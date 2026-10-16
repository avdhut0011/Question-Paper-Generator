"""Adapters for the original QPG screens, with authenticated private jobs."""
import hashlib
import json
import uuid
from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from sqlalchemy import func

from . import db
from .models import Artifact, GenerationJob, utcnow
from .security import audit, may_teach, private_path, scope


def curriculum():
    result = {key: request.form.get(key, '').strip() for key in ('grade', 'subject', 'board')}
    if not all(result.values()) or any(len(value) > 100 for value in result.values()):
        raise ValueError('Please provide grade, subject, and board.')
    if not may_teach(current_user, **result):
        abort(403)
    return result


def positive_field(name, maximum=1000):
    try:
        value = int(request.form.get(name, '0'))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name.replace("_", " ").capitalize()} must be a positive integer.') from exc
    if not 1 <= value <= maximum:
        raise ValueError(f'{name.replace("_", " ").capitalize()} must be between 1 and {maximum}.')
    return value


def enqueue(kind, details, fields):
    from .routes import enforce_quota
    enforce_quota()
    identifier = str(uuid.uuid4())
    workdir = private_path(identifier)
    workdir.mkdir(parents=True)
    uploads = {}
    for field, extensions in fields.items():
        upload = request.files.get(field)
        if upload and upload.filename:
            extension = Path(upload.filename).suffix.lower()
            if extension not in extensions:
                raise ValueError(f'Unsupported {field.replace("_", " ")} format. Use {", ".join(sorted(extensions))}.')
            target = workdir / ('input_' + field + extension)
            upload.save(target)
            uploads[field] = target.relative_to(Path(current_app.config['STORAGE_ROOT']).resolve()).as_posix()
    record = GenerationJob(id=identifier, user_id=current_user.id, school_id=current_user.school_id,
        kind=kind, parameters={'mode': 'original', 'blueprint': details,
            'inputs': uploads, 'options': request.form.to_dict(flat=False)})
    if not record.school_id:
        raise ValueError('Your account needs a school assignment before generation.')
    db.session.add(record)
    audit('generation.queued', identifier, interface='original', kind=kind)
    db.session.commit()
    return redirect(url_for('platform.job', job_id=identifier))


def generate_questions():
    if request.method == 'POST':
        try:
            details = curriculum()
            topic = request.form.get('topic', '').strip()
            if not topic or len(topic) > 200:
                raise ValueError('Please enter a topic (up to 200 characters).')
            types = request.form.getlist('question_types[]')
            supported = {'MCQ', 'Short Answer', 'Long Answer', 'Very Long Answer', 'Fill in the Blanks', 'Matching', 'True/False', 'Numerical'}
            if not types or any(qtype not in supported for qtype in types) or len(set(types)) != len(types):
                raise ValueError('Please select valid question types.')
            counts = {qtype: positive_field(f'count_for_type[{qtype}]', 100) for qtype in types}
            marks = {qtype: positive_field(f'marks_for_type[{qtype}]', 100) for qtype in types}
            if sum(counts.values()) > 100:
                raise ValueError('Generate at most 100 questions per request.')
            if request.form.get('export_format', 'excel') not in {'excel', 'word'}:
                raise ValueError('Choose Excel or Word export.')
            details.update(title='Question bank: ' + topic, topic=topic, academic_year='',
                num_questions=sum(counts.values()), total_marks=sum(counts[t]*marks[t] for t in types),
                counts=counts, marks=marks)
            return enqueue('original_bank', details, {'syllabus': {'.pdf', '.txt'}})
        except ValueError as exc:
            db.session.rollback(); flash(str(exc), 'danger')
    return render_template('question_generation.html')


def generate_paper():
    if request.method == 'POST':
        try:
            details = curriculum()
            details.update(title='Question paper', academic_year='', total_marks=positive_field('total_marks'),
                           num_questions=positive_field('num_questions', 100))
            if details['total_marks'] < details['num_questions']:
                raise ValueError('Total marks cannot be less than the number of questions.')
            try:
                difficulty = {key: int(request.form.get(key + '_questions', 0)) for key in ('easy', 'medium', 'hard')}
            except ValueError as exc:
                raise ValueError('Enter valid difficulty percentages.') from exc
            if any(value < 0 or value > 100 for value in difficulty.values()) or sum(difficulty.values()) != 100:
                raise ValueError('Easy, medium, and hard percentages must total 100%.')
            details['difficulty'] = difficulty
            if request.form.get('paper_template', 'default') not in {'default', 'aus', 'aga'}:
                raise ValueError('Choose a supported paper template.')
            if request.form.get('use_question_bank_only') == 'on':
                upload = request.files.get('question_bank')
                if not upload or not upload.filename:
                    raise ValueError('Upload a question bank when using question-bank mode.')
            return enqueue('original_paper', details, {'syllabus': {'.pdf', '.txt'}, 'sample_paper': {'.pdf', '.txt'},
                'question_bank': {'.xlsx', '.csv'}, 'paper_blueprint': {'.pdf', '.txt'}})
        except ValueError as exc:
            db.session.rollback(); flash(str(exc), 'danger')
    return render_template('question_paper.html')


def upload_question_bank():
    if request.method == 'POST':
        try:
            details = curriculum()
            details.update(title='Populated question bank', academic_year='', total_marks=0,
                           num_questions=positive_field('num_questions', 100))
            upload = request.files.get('question_bank')
            if not upload or not upload.filename:
                raise ValueError('Please select an XLSX question bank.')
            return enqueue('original_population', details, {'question_bank': {'.xlsx'}})
        except ValueError as exc:
            db.session.rollback(); flash(str(exc), 'danger')
    return render_template('upload_question_bank.html')


def authorized_artifact(identifier):
    artifact = db.session.get(Artifact, identifier)
    if not artifact:
        abort(404)
    job = scope(db.session.query(GenerationJob), GenerationJob).filter_by(id=artifact.job_id).first_or_404()
    if job.status != 'completed':
        abort(404)
    if job.paper and job.paper.status != 'approved':
        abort(403)
    path = private_path(artifact.storage_key)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact.checksum:
        abort(409)
    return artifact, job, path


def serve_artifact(filename, download=False):
    artifact, job, path = authorized_artifact(filename)
    audit('artifact.downloaded' if download else 'artifact.previewed', artifact.id)
    db.session.commit()
    response = send_file(path, as_attachment=download, download_name=artifact.name)
    if artifact.kind == 'html':
        response.headers['Content-Security-Policy'] = "sandbox allow-same-origin; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"
    return response


def preview_job(job_id):
    job = scope(db.session.query(GenerationJob), GenerationJob).filter_by(id=job_id).first_or_404()
    if job.status != 'completed' or not job.kind.startswith('original_'):
        abort(404)
    artifacts = {a.kind: a for a in job.artifacts}
    main = next((artifacts[k] for k in ('pdf', 'word', 'excel', 'html') if k in artifacts), None)
    if not main:
        abort(404)
    return render_template('preview.html', filename=main.id, file_type=main.kind,
        tex_filename=artifacts['latex'].id if 'latex' in artifacts else None,
        html_filename=artifacts['html'].id if 'html' in artifacts else None,
        download_names={artifact.id: artifact.name for artifact in job.artifacts},
        job_id=job.id)


def register_original_ui(app):
    app.add_url_rule('/', endpoint='index', view_func=lambda: render_template('index.html'))
    app.add_url_rule('/generate_questions', endpoint='generate_questions', view_func=generate_questions, methods=['GET', 'POST'])
    app.add_url_rule('/generate_paper', endpoint='generate_qp', view_func=generate_paper, methods=['GET', 'POST'])
    app.add_url_rule('/upload_question_bank', endpoint='upload_question_bank', view_func=upload_question_bank, methods=['GET', 'POST'])
    app.add_url_rule('/chat', endpoint='chat', view_func=lambda: render_template('chat.html'))
    app.add_url_rule('/uploads/<filename>', endpoint='serve_upload', view_func=serve_artifact)
    app.add_url_rule('/download/<filename>', endpoint='download', view_func=lambda filename: serve_artifact(filename, True))
    app.add_url_rule('/jobs/<job_id>/preview', endpoint='preview_job', view_func=preview_job)
    from .original_chat import chat_api, chat_upload
    app.add_url_rule('/api/chat', endpoint='api_chat', view_func=chat_api, methods=['POST'])
    app.add_url_rule('/api/chat/upload', endpoint='api_chat_upload', view_func=chat_upload, methods=['POST'])
