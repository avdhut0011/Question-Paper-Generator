import hashlib
import json
from datetime import timedelta
from pathlib import Path

from flask import current_app, render_template
from sqlalchemy import select
from . import db
from .models import Artifact, AuditEvent, GenerationJob, Paper, Question, School, SourceDocument, User, utcnow
from .security import may_teach, private_path
from .validation import fingerprint, matches, select_bank_questions, validate_blueprint, validate_paper, validate_question


def add_artifact(job, path, kind):
    root = Path(current_app.config['STORAGE_ROOT']).resolve()
    path = Path(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Artifact is outside private storage.')
    artifact = Artifact(job_id=job.id, storage_key=path.relative_to(root).as_posix(),
                        name=path.name, kind=kind, checksum=hashlib.sha256(path.read_bytes()).hexdigest())
    db.session.add(artifact)
    return artifact


def run_next_job():
    """Claim one durable job. PostgreSQL SKIP LOCKED permits multiple workers."""
    job = db.session.execute(select(GenerationJob).where(GenerationJob.status == 'queued')
                             .order_by(GenerationJob.created_at, GenerationJob.id)
                             .with_for_update(skip_locked=True).limit(1)).scalar_one_or_none()
    if not job:
        db.session.rollback()
        return False
    job.status = 'running'
    job.started_at = utcnow()
    job_id = job.id
    db.session.commit()
    try:
        process_job(job)
    except Exception as exc:
        metrics = dict(job.metrics or {})
        db.session.rollback()
        job = db.session.get(GenerationJob, job_id)
        job.status = 'failed'
        job.metrics = metrics
        # Provider errors can contain request URLs/keys. Store detailed validation
        # errors only; operational details remain in protected server logs.
        job.error = str(exc)[:2000] if isinstance(exc, ValueError) else 'Generation failed. Ask an administrator to inspect the worker logs.'
        job.finished_at = utcnow()
        db.session.add(AuditEvent(user_id=job.user_id, action='generation.failed', target_id=job.id))
        db.session.commit()
        current_app.logger.error('Generation job %s failed (%s)', job_id, type(exc).__name__)
    return True


def process_job(job):
    if job.kind.startswith('original_'):
        from .original_jobs import process_original_job
        return process_original_job(job)
    from .provider import generate_slot
    from .rendering import compile_pdf, render_latex
    params = job.parameters
    blueprint = validate_blueprint(params['blueprint'])
    teacher = db.session.get(User, job.user_id)
    if not teacher or not teacher.active or teacher.school_id != job.school_id and teacher.role != 'group_admin':
        raise ValueError('The requester no longer has access to this school.')
    if not may_teach(teacher, blueprint['grade'], blueprint['subject'], blueprint['board']):
        raise ValueError('The teaching assignment no longer permits this paper.')
    # Serialize selection per school so simultaneous jobs cannot both pass the
    # recent-use check before either paper has been committed.
    school = db.session.execute(select(School).where(School.id == job.school_id).with_for_update()).scalar_one()
    excluded = set()
    cutoff = utcnow() - timedelta(days=90)
    previous = db.session.query(Paper).filter(Paper.school_id == job.school_id, Paper.created_at >= cutoff).all()
    for paper in previous:
        excluded.update(fingerprint(q['stem']) for q in paper.snapshot['questions'])
    questions, usages, passages = [], [], None
    if params['mode'] == 'bank':
        records = db.session.query(Question).filter_by(
            school_id=job.school_id, grade=blueprint['grade'], subject=blueprint['subject'],
            board=blueprint['board'], approved=True).order_by(Question.created_at, Question.id).all()
        candidates = [dict(record.content, bank_id=record.id) for record in records]
        questions = select_bank_questions(candidates, blueprint, excluded)
    elif params['mode'] in {'ai', 'revision'}:
        if params['mode'] == 'revision':
            parent = db.session.get(Paper, params.get('parent_id'))
            if not parent or parent.school_id != job.school_id or parent.user_id != job.user_id:
                raise ValueError('Invalid parent paper for revision.')
            questions = params['questions']
            if not params.get('source_id'):
                # Manual revisions are drafts requiring a fresh human approval.
                validate_paper(questions, blueprint)
            else:
                source = db.session.get(SourceDocument, params.get('source_id'))
                if not source or source.school_id != job.school_id:
                    raise ValueError('Original approved source is unavailable.')
                passages = source.passages
                validate_paper(questions, blueprint, passages)
        else:
            source = db.session.get(SourceDocument, params.get('source_id'))
        if params['mode'] == 'ai' and (not source or source.school_id != job.school_id or any(
                getattr(source, field) != blueprint[field] for field in ('grade', 'subject', 'board'))):
            raise ValueError('Choose an approved source matching the school, board, grade, and subject.')
        if params['mode'] == 'ai':
            passages = source.passages
        for slot in blueprint['slots'] if params['mode'] == 'ai' else []:
            error = ''
            for attempt in range(3):
                drafts, usage = generate_slot(slot, passages, [q['stem'] for q in questions], error,
                                              {key: blueprint[key] for key in ('grade', 'subject', 'board', 'academic_year')})
                usages.append(dict(usage, slot=len(questions), attempt=attempt + 1))
                job.metrics = {'attempts': list(usages), 'model': current_app.config['GEMINI_MODEL'],
                               'schema_version': 1, 'prompt_version': 1}
                try:
                    if len(drafts) != slot['count']:
                        raise ValueError('Wrong number of questions for this slot.')
                    seen = excluded | {fingerprint(q['stem']) for q in questions}
                    for q in drafts:
                        validate_question(q, passages)
                        if not matches(q, slot) or fingerprint(q['stem']) in seen:
                            raise ValueError('Question does not match the slot, or repeats an existing question.')
                        seen.add(fingerprint(q['stem']))
                    questions.extend(drafts)
                    break
                except ValueError as exc:
                    error = str(exc)
            else:
                raise ValueError('Question validation failed after three attempts: ' + error)
    else:
        raise ValueError('Unknown question source mode.')
    validate_paper(questions, blueprint, passages)
    snapshot = {'schema_version': 1, 'prompt_version': 1, 'blueprint': blueprint,
                'questions': questions, 'mode': params['mode'], 'usage': usages,
                'model': current_app.config['GEMINI_MODEL'] if params['mode'] == 'ai' else None,
                'source_id': params.get('source_id'),
                'source_version': source.version if passages is not None else None,
                'validation': {'hard_constraints': 'passed', 'factual_review': 'pending'}}
    workdir = private_path(job.id)
    workdir.mkdir(parents=True, exist_ok=False)
    tex = workdir / 'paper.tex'
    tex.write_text(render_latex(snapshot, school.name), encoding='utf-8')
    html = workdir / 'paper.html'
    html.write_text(render_template('platform/paper_document.html', snapshot=snapshot, school=school,
                                    answers=False), encoding='utf-8')
    answers = workdir / 'answer_key.json'
    answers.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    add_artifact(job, tex, 'latex')
    add_artifact(job, html, 'html')
    add_artifact(job, answers, 'answers')
    if current_app.config['REQUIRE_PDF']:
        add_artifact(job, compile_pdf(tex), 'pdf')
    paper = Paper(job_id=job.id, school_id=job.school_id, user_id=job.user_id,
                  parent_id=params.get('parent_id'), snapshot=snapshot)
    db.session.add(paper)
    job.status = 'completed'
    job.finished_at = utcnow()
    db.session.add(AuditEvent(user_id=job.user_id, action='generation.completed', target_id=job.id))
    db.session.commit()
