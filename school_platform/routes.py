import hashlib
import json
import secrets
import uuid
from datetime import timedelta, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .models import Artifact, AuditEvent, GenerationJob, LoginAttempt, Paper, Question, School, SourceDocument, TeachingAssignment, User, utcnow
from .security import admin_required, audit, may_teach, private_path, scope
from .validation import fingerprint, text, validate_blueprint, validate_paper, validate_question

routes = Blueprint('platform', __name__)
DUMMY_PASSWORD_HASH = generate_password_hash('unusable-placeholder-password')


def school_choices():
    query = db.session.query(School)
    if current_user.role != 'group_admin':
        query = query.filter_by(id=current_user.school_id)
    return query.order_by(School.name).all()


def selected_school():
    school_id = request.form.get('school_id') if current_user.role == 'group_admin' else current_user.school_id
    if not school_id or not db.session.get(School, school_id):
        raise ValueError('Select a valid school.')
    return school_id


def enforce_quota():
    # Serialize submissions from the same user so quota checks cannot race.
    db.session.execute(select(User.id).where(User.id == current_user.id).with_for_update()).first()
    active = db.session.query(func.count(GenerationJob.id)).filter(
        GenerationJob.user_id == current_user.id, GenerationJob.status.in_(['queued', 'running'])).scalar()
    daily = db.session.query(func.count(GenerationJob.id)).filter(
        GenerationJob.user_id == current_user.id, GenerationJob.created_at >= utcnow() - timedelta(days=1)).scalar()
    if active >= 3 or daily >= 30:
        raise ValueError('Generation limit reached: at most 3 active jobs and 30 attempts per day.')


@routes.route('/')
def home():
    return render_template('index.html')


@routes.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        # Hash the direct peer address; only trust proxy headers if configured by the deployment.
        address_hash = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
        cutoff = utcnow() - timedelta(minutes=15)
        attempts = db.session.query(func.count(LoginAttempt.id)).filter(
            LoginAttempt.address_hash == address_hash, LoginAttempt.created_at >= cutoff).scalar()
        if attempts >= 30:
            return render_template('platform/login.html', error='Too many attempts. Try again in 15 minutes.'), 429
        db.session.add(LoginAttempt(address_hash=address_hash))
        db.session.commit()
        email = request.form.get('email', '').strip().casefold()[:254]
        user = db.session.execute(select(User).where(User.email == email).with_for_update()).scalar_one_or_none()
        locked = user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > utcnow()
        password = request.form.get('password', '')[:1024]
        valid = user.check_password(password) if user else check_password_hash(DUMMY_PASSWORD_HASH, password)
        if not user or not user.active or locked or not valid:
            if user and not locked:
                user.failed_logins += 1
                if user.failed_logins >= 5:
                    user.locked_until = utcnow() + timedelta(minutes=15)
                    user.failed_logins = 0
            db.session.add(AuditEvent(action='login.failed'))
            db.session.commit()
            return render_template('platform/login.html', error='Invalid credentials or account temporarily unavailable.'), 401
        user.failed_logins, user.locked_until = 0, None
        session.clear()
        login_user(user)
        session.permanent = True
        audit('login.success', user.id)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('platform/login.html')


@routes.post('/logout')
def logout():
    audit('logout', current_user.id)
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for('platform.login'))


@routes.route('/password', methods=['GET', 'POST'])
def password():
    if request.method == 'POST':
        if not current_user.check_password(request.form.get('current_password', '')):
            flash('Current password is incorrect.', 'danger')
        else:
            try:
                new = request.form.get('password', '')
                if new != request.form.get('confirm_password'):
                    raise ValueError('New passwords do not match.')
                current_user.set_password(new)
                current_user.must_change_password = False
                current_user.session_version += 1
                audit('password.changed', current_user.id)
                db.session.commit()
                login_user(current_user._get_current_object())
                flash('Password updated. Other sessions have been revoked.', 'success')
                return redirect(url_for('platform.history'))
            except ValueError as exc:
                flash(str(exc), 'danger')
    return render_template('platform/password.html')


@routes.get('/history')
def history():
    query = scope(db.session.query(GenerationJob), GenerationJob)
    status = request.args.get('status', '').strip()
    subject = request.args.get('subject', '').strip()
    if status:
        query = query.filter(GenerationJob.status == status)
    if subject:
        query = query.filter(GenerationJob.parameters['blueprint']['subject'].as_string() == subject)
    if current_user.role != 'teacher':
        if request.args.get('teacher'):
            query = query.join(User).filter(User.email == request.args['teacher'].strip().casefold())
        if request.args.get('school'):
            query = query.filter(GenerationJob.school_id == request.args['school'])
    pagination = query.order_by(GenerationJob.created_at.desc()).paginate(
                             page=request.args.get('page', 1, type=int), per_page=25, error_out=False)
    return render_template('platform/history.html', pagination=pagination, schools=school_choices())


DEFAULT_BLUEPRINT = {
    'title': 'Assessment', 'academic_year': '2026–2027', 'grade': '6', 'subject': 'Mathematics',
    'board': 'CBSE', 'duration_minutes': 60, 'total_marks': 10, 'num_questions': 4,
    'slots': [
        {'type': 'MCQ', 'marks': 1, 'count': 2, 'chapter': 'Fractions', 'difficulty': 'easy', 'bloom': 'Understand'},
        {'type': 'Short Answer', 'marks': 4, 'count': 2, 'chapter': 'Fractions', 'difficulty': 'medium', 'bloom': 'Apply'},
    ],
}


@routes.route('/papers/new', methods=['GET', 'POST'])
def new_paper():
    if request.method == 'POST':
        try:
            request_id = str(uuid.UUID(request.form.get('request_id', '')))
            existing = db.session.get(GenerationJob, request_id)
            if existing:
                if existing.user_id != current_user.id:
                    abort(404)
                return redirect(url_for('platform.job', job_id=existing.id))
            blueprint = validate_blueprint(json.loads(request.form.get('blueprint', '{}')))
            if not may_teach(current_user, blueprint['grade'], blueprint['subject'], blueprint['board']):
                abort(403)
            school_id = selected_school()
            mode = request.form.get('mode')
            if mode not in {'ai', 'bank'}:
                raise ValueError('Choose approved bank or AI drafts.')
            enforce_quota()
            parameters = {'blueprint': blueprint, 'mode': mode}
            if mode == 'ai':
                source = scope(db.session.query(SourceDocument), SourceDocument).filter_by(
                    id=request.form.get('source_id'), school_id=school_id).first()
                if not source or any(getattr(source, key) != blueprint[key] for key in ('grade', 'subject', 'board')):
                    raise ValueError('Choose an approved source matching this school and curriculum.')
                parameters['source_id'] = source.id
            job_record = GenerationJob(id=request_id, school_id=school_id, user_id=current_user.id, parameters=parameters)
            db.session.add(job_record)
            audit('generation.queued', job_record.id)
            db.session.commit()
            return redirect(url_for('platform.job', job_id=job_record.id))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        except IntegrityError:
            db.session.rollback()
            existing = db.session.get(GenerationJob, request.form.get('request_id'))
            if not existing or existing.user_id != current_user.id:
                abort(409)
            return redirect(url_for('platform.job', job_id=existing.id))
    sources = scope(db.session.query(SourceDocument), SourceDocument).order_by(SourceDocument.created_at.desc()).all()
    return render_template('platform/new_paper.html', schools=school_choices(), sources=sources,
                            blueprint=request.form.get('blueprint') or json.dumps(DEFAULT_BLUEPRINT, indent=2, ensure_ascii=False),
                            request_id=request.form.get('request_id') or str(uuid.uuid4()))


@routes.get('/jobs/<job_id>')
def job(job_id):
    record = scope(db.session.query(GenerationJob), GenerationJob).filter_by(id=job_id).first_or_404()
    return render_template('platform/job.html', job=record)


@routes.post('/jobs/<job_id>/cancel')
def cancel_job(job_id):
    record = scope(db.session.query(GenerationJob), GenerationJob).filter_by(id=job_id).with_for_update().first_or_404()
    if record.status != 'queued':
        abort(409, 'Only queued jobs can be cancelled.')
    record.status, record.finished_at = 'cancelled', utcnow()
    audit('generation.cancelled', record.id)
    db.session.commit()
    return redirect(url_for('platform.job', job_id=record.id))


@routes.get('/papers/<paper_id>')
def paper(paper_id):
    record = scope(db.session.query(Paper), Paper).filter_by(id=paper_id).first_or_404()
    return render_template('platform/paper.html', paper=record, snapshot=record.snapshot,
                            school=db.session.get(School, record.school_id))


@routes.post('/papers/<paper_id>/submit')
def submit_paper(paper_id):
    record = scope(db.session.query(Paper), Paper).filter_by(id=paper_id).with_for_update().first_or_404()
    if record.status not in {'draft', 'rejected'}:
        abort(409)
    record.status = 'submitted'
    audit('paper.submitted', record.id)
    db.session.commit()
    return redirect(url_for('platform.paper', paper_id=record.id))


@routes.route('/papers/<paper_id>/revise', methods=['GET', 'POST'])
def revise_paper(paper_id):
    parent = scope(db.session.query(Paper), Paper).filter_by(id=paper_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        try:
            enforce_quota()
            request_id = str(uuid.UUID(request.form.get('request_id', '')))
            existing = db.session.get(GenerationJob, request_id)
            if existing:
                if existing.user_id != current_user.id:
                    abort(404)
                return redirect(url_for('platform.job', job_id=existing.id))
            questions = json.loads(request.form.get('questions', '[]'))
            validate_paper(questions, parent.snapshot['blueprint'])
            questions = [{key: value for key, value in question.items() if key != 'bank_id'} for question in questions]
            parameters = {'mode': 'revision', 'parent_id': parent.id, 'questions': questions,
                          'blueprint': parent.snapshot['blueprint'], 'source_id': parent.snapshot.get('source_id')}
            record = GenerationJob(id=request_id, school_id=parent.school_id, user_id=current_user.id, parameters=parameters)
            db.session.add(record)
            audit('paper.revision_queued', parent.id, job=record.id)
            db.session.commit()
            return redirect(url_for('platform.job', job_id=record.id))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        except IntegrityError:
            db.session.rollback()
            abort(409, 'Revision already submitted.')
    return render_template('platform/revise.html', paper=parent,
        questions=request.form.get('questions') or json.dumps(parent.snapshot['questions'], ensure_ascii=False, indent=2),
        request_id=request.form.get('request_id') or str(uuid.uuid4()))


@routes.post('/papers/<paper_id>/review')
@admin_required
def review_paper(paper_id):
    record = scope(db.session.query(Paper), Paper).filter_by(id=paper_id).with_for_update().first_or_404()
    if record.status != 'submitted' or record.user_id == current_user.id:
        abort(409, 'A different administrator must review a submitted paper.')
    decision = request.form.get('decision')
    if decision not in {'approved', 'rejected'}:
        abort(400)
    if decision == 'approved' and request.form.get('checked') != 'yes':
        abort(400, 'Confirm that questions, answers, and marking schemes have been reviewed.')
    note = request.form.get('note', '').strip()[:4000]
    if decision == 'rejected' and not note:
        abort(400, 'Explain the changes needed before rejecting a paper.')
    validate_paper(record.snapshot['questions'], record.snapshot['blueprint'])
    record.status, record.reviewed_by, record.reviewed_at, record.review_note = decision, current_user.id, utcnow(), note
    if decision == 'approved' and request.form.get('publish_questions') == 'yes':
        curriculum = {key: record.snapshot['blueprint'][key] for key in ('grade', 'subject', 'board')}
        existing = db.session.query(Question).filter_by(school_id=record.school_id, **curriculum).all()
        stems = {fingerprint(item.content['stem']) for item in existing}
        count = 0
        for question in record.snapshot['questions']:
            key = fingerprint(question['stem'])
            if key not in stems:
                content = {field: value for field, value in question.items() if field != 'bank_id'}
                db.session.add(Question(school_id=record.school_id, content=content, approved=True,
                                       created_by=current_user.id, **curriculum))
                stems.add(key)
                count += 1
        audit('questions.published_from_paper', record.id, count=count)
    audit('paper.' + decision, record.id)
    db.session.commit()
    return redirect(url_for('platform.paper', paper_id=record.id))


@routes.get('/artifacts/<artifact_id>')
def artifact(artifact_id):
    record = db.session.get(Artifact, artifact_id)
    if not record:
        abort(404)
    job_record = scope(db.session.query(GenerationJob), GenerationJob).filter_by(id=record.job_id).first_or_404()
    if job_record.status != 'completed':
        abort(404)
    if job_record.paper and job_record.paper.status != 'approved':
        abort(403, 'Final downloads are available after an administrator approves the paper. Review the draft on the paper page.')
    path = private_path(record.storage_key)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record.checksum:
        abort(409, 'Artifact is missing or failed its integrity check.')
    audit('artifact.downloaded', record.id, kind=record.kind)
    db.session.commit()
    return send_file(path, as_attachment=True, download_name=record.name)


@routes.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            if action == 'school':
                if current_user.role != 'group_admin':
                    abort(403)
                record = School(name=text(request.form.get('name'), 'School name', 160))
                db.session.add(record)
                db.session.flush()
                audit('school.created', record.id)
            elif action == 'user':
                role = request.form.get('role')
                if role not in {'teacher', 'school_admin', 'group_admin'}:
                    raise ValueError('Invalid role.')
                if current_user.role != 'group_admin' and role != 'teacher':
                    abort(403)
                email = text(request.form.get('email'), 'Email', 254).casefold()
                if '@' not in email:
                    raise ValueError('Provide a valid staff email.')
                record = User(name=text(request.form.get('name'), 'Name', 160), email=email,
                              school_id=selected_school(), role=role)
                record.set_password(request.form.get('password', ''))
                db.session.add(record)
                db.session.flush()
                audit('user.created', record.id)
            elif action in {'toggle_user', 'reset_password', 'assignment'}:
                record = scope(db.session.query(User), User).filter_by(id=request.form.get('user_id')).with_for_update().first_or_404()
                if record.id == current_user.id or current_user.role != 'group_admin' and record.role != 'teacher':
                    abort(403)
                if action == 'toggle_user':
                    record.active = not record.active
                    record.session_version += 1
                elif action == 'reset_password':
                    record.set_password(request.form.get('password', ''))
                    record.must_change_password = True
                    record.session_version += 1
                    record.failed_logins, record.locked_until = 0, None
                else:
                    db.session.add(TeachingAssignment(user_id=record.id,
                        grade=text(request.form.get('grade'), 'Grade', 20),
                        subject=text(request.form.get('subject'), 'Subject', 100),
                        board=text(request.form.get('board'), 'Board', 50)))
                audit('user.' + action, record.id)
            elif action == 'remove_assignment':
                record = db.session.get(TeachingAssignment, request.form.get('assignment_id'))
                if not record:
                    abort(404)
                user = scope(db.session.query(User), User).filter_by(id=record.user_id).first_or_404()
                if current_user.role != 'group_admin' and user.role != 'teacher':
                    abort(403)
                audit('assignment.removed', record.id)
                db.session.delete(record)
            else:
                raise ValueError('Unknown action.')
            db.session.commit()
            flash('Saved.', 'success')
            return redirect(url_for('platform.admin'))
        except (ValueError, IntegrityError) as exc:
            db.session.rollback()
            flash(str(exc) if isinstance(exc, ValueError) else 'This record already exists.', 'danger')
    users = scope(db.session.query(User), User).order_by(User.name).all()
    assignments = db.session.query(TeachingAssignment).filter(TeachingAssignment.user_id.in_([u.id for u in users])).all()
    return render_template('platform/admin.html', schools=school_choices(), users=users, assignments=assignments)


@routes.route('/admin/library', methods=['GET', 'POST'])
@admin_required
def library():
    if request.method == 'POST':
        try:
            school_id = selected_school()
            curriculum = {key: text(request.form.get(key), key, 100) for key in ('grade', 'subject', 'board')}
            action = request.form.get('action')
            if action == 'source':
                from .importing import source_passages
                upload = request.files.get('content_file')
                raw = request.form.get('content', '').strip()
                if upload and upload.filename:
                    passages = source_passages(upload)
                else:
                    passages = {f'passage-{i + 1}': part.strip() for i, part in enumerate(raw.split('\n\n')) if part.strip()}
                if not isinstance(passages, dict) or not passages or len(json.dumps(passages)) > 100000:
                    raise ValueError('Provide approved passages as a JSON object, up to 100,000 characters.')
                for reference, passage in passages.items():
                    text(reference, 'Passage reference', 160)
                    text(passage, 'Passage text', 25000)
                record = SourceDocument(school_id=school_id, name=text(request.form.get('name'), 'Source name', 160),
                    version=text(request.form.get('version'), 'Version', 80), passages=passages,
                    created_by=current_user.id, **curriculum)
                db.session.add(record)
                db.session.flush()
                audit('source.approved', record.id)
            elif action == 'questions':
                from .importing import bank_questions
                upload = request.files.get('content_file')
                items = bank_questions(upload) if upload and upload.filename else json.loads(request.form.get('content', '[]'))
                if not isinstance(items, list) or not 1 <= len(items) <= 500:
                    raise ValueError('Import a JSON array of 1–500 reviewed questions.')
                for q in items:
                    content = validate_question(q)
                    db.session.add(Question(school_id=school_id, content=content, approved=True,
                                           created_by=current_user.id, **curriculum))
                audit('questions.imported', count=len(items), school=school_id)
            else:
                raise ValueError('Unknown library action.')
            db.session.commit()
            flash('Approved library material saved.', 'success')
            return redirect(url_for('platform.library'))
        except (ValueError, TypeError, IntegrityError) as exc:
            db.session.rollback()
            flash('This source version already exists. Publish a new version.' if isinstance(exc, IntegrityError) else str(exc), 'danger')
    return render_template('platform/library.html', schools=school_choices(),
                            sources=scope(db.session.query(SourceDocument), SourceDocument).all(),
                            question_count=scope(db.session.query(Question), Question).count())


@routes.get('/admin/library/template')
@admin_required
def library_template():
    from .importing import bank_template
    return send_file(bank_template(), as_attachment=True, download_name='reviewed_question_bank.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@routes.get('/admin/audit')
@admin_required
def audit_log():
    query = db.session.query(AuditEvent)
    if current_user.role != 'group_admin':
        query = query.join(User, AuditEvent.user_id == User.id).filter(User.school_id == current_user.school_id)
    pagination = query.order_by(AuditEvent.created_at.desc()).paginate(
                             page=request.args.get('page', 1, type=int), per_page=50, error_out=False)
    return render_template('platform/audit.html', pagination=pagination)
