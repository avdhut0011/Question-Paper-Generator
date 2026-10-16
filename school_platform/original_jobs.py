"""Run the original generation workflows in isolated, private job directories."""
import os
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g
from . import db
from .models import AuditEvent, User, utcnow
from .security import may_teach, private_path


@contextmanager
def job_directory(path):
    # Workers execute one job at a time per process; HTTP requests never change cwd.
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def process_original_job(job):
    from .jobs import add_artifact
    details = job.parameters['blueprint']
    options = job.parameters['options']
    def value(key, default=''):
        return options.get(key, [default])[0]
    teacher = db.session.get(User, job.user_id)
    if not teacher or not teacher.active or teacher.role != 'group_admin' and teacher.school_id != job.school_id:
        raise ValueError('The requester no longer has access to this school.')
    if not may_teach(teacher, details['grade'], details['subject'], details['board']):
        raise ValueError('The teaching assignment no longer permits this request.')
    inputs = {field: str(private_path(key)) for field, key in job.parameters.get('inputs', {}).items()}
    workdir = private_path(job.id)
    workdir.mkdir(parents=True, exist_ok=True)
    g.qpg_usage = []
    artifacts = []
    if job.kind == 'original_bank':
        from qg_model import generate_question_bank
        with job_directory(workdir):
            result = generate_question_bank(grade=details['grade'], subject=details['subject'], topic=details['topic'],
                question_types=list(details['counts']), marks_map=details['marks'], count_map=details['counts'],
                num_questions=details['num_questions'], board=details['board'], blooms_levels=options.get('blooms_levels', []),
                syllabus_path=inputs.get('syllabus'), custom_prompt=value('custom_prompt'),
                include_images=value('include_images') == 'on', export_format=value('export_format', 'excel'))
            if not result:
                raise ValueError('Question bank generation failed validation.')
            path = Path(result).resolve()
            if not path.is_file():
                raise ValueError('Question bank output was not created.')
            artifacts.append((path, 'word' if path.suffix == '.docx' else 'excel'))
    elif job.kind == 'original_population':
        with job_directory(workdir):
            artifacts.append((populate_original_bank(details, inputs['question_bank'], options).resolve(), 'excel'))
    elif job.kind == 'original_paper':
        from services.paper_service import generate_question_paper
        with job_directory(workdir):
            pdf, tex, html, error = generate_question_paper(grade=details['grade'], subject=details['subject'],
                total_marks=details['total_marks'], difficulty_split=details['difficulty'], num_questions=details['num_questions'],
                board=details['board'], blooms_levels=options.get('blooms_levels', []),
                custom_instructions=value('custom_instructions'), syllabus_path=inputs.get('syllabus'),
                sample_path=inputs.get('sample_paper'), include_images=value('include_images') == 'on',
                question_bank_path=inputs.get('question_bank'), use_question_bank_only=value('use_question_bank_only') == 'on',
                paper_template=value('paper_template', 'default'), blueprint_path=inputs.get('paper_blueprint'))
            if error:
                raise ValueError(error)
            for path, kind in ((pdf, 'pdf'), (tex, 'latex')):
                if path and Path(path).is_file():
                    artifacts.append((Path(path).resolve(), kind))
            if html:
                html_path = workdir / 'preview.html'
                # Use artifact IDs for embedded images instead of public filesystem paths.
                for image in (workdir / 'uploads').glob('*.png'):
                    asset = add_artifact(job, image, 'image')
                    db.session.flush()
                    html = html.replace('/uploads/' + image.name, '/uploads/' + asset.id)
                html_path.write_text(html, encoding='utf-8')
                artifacts.append((html_path, 'html'))
    else:
        raise ValueError('Unknown original workflow.')
    if not artifacts:
        raise ValueError('No validated output was produced.')
    for path, kind in artifacts:
        if not path.resolve().is_relative_to(workdir.resolve()):
            raise ValueError('Generated output is outside this job directory.')
        add_artifact(job, path, kind)
    job.metrics = {'model': current_app.config['GEMINI_MODEL'], 'attempts': g.qpg_usage,
                   'interface': 'original', 'output_count': len(artifacts)}
    job.status, job.finished_at = 'completed', utcnow()
    db.session.add(AuditEvent(user_id=job.user_id, action='generation.completed', target_id=job.id,
                              details={'interface': 'original', 'kind': job.kind}))
    db.session.commit()


def populate_original_bank(details, bank_path, options):
    import pandas as pd
    from qg_model import generate_questions
    from .validation import fingerprint
    frame = pd.read_excel(bank_path).fillna('')
    frame.columns = frame.columns.str.strip().str.lower()
    required = {'topic', 'question type', 'marks', 'question'}
    if not required <= set(frame.columns) or frame.empty:
        raise ValueError('Question bank must contain Topic, Question Type, Marks, and Question columns with at least one row.')
    profiles = []
    for _, row in frame.iterrows():
        try:
            profile = (str(row['topic']).strip(), str(row['question type']).strip(), int(row['marks']))
        except (ValueError, TypeError) as exc:
            raise ValueError('Existing question-bank marks must be positive whole numbers.') from exc
        if not profile[0] or profile[2] < 1:
            raise ValueError('Every existing question needs a topic and positive marks.')
        if profile not in profiles:
            profiles.append(profile)
    rows = []
    used = {fingerprint(str(q)) for q in frame['question']}
    for index, (topic, qtype, marks) in enumerate(profiles[:details['num_questions']]):
        count = details['num_questions'] // min(len(profiles), details['num_questions'])
        count += index < details['num_questions'] % min(len(profiles), details['num_questions'])
        prompt = options.get('custom_prompt', [''])[0] + '\nDo not repeat these existing questions:\n' + '\n'.join(str(q) for q in frame['question'].tolist()[:100])
        questions, choices, types, generated_marks = generate_questions(details['grade'], details['subject'], topic,
            [qtype], {qtype: marks}, {qtype: count}, details['board'], options.get('blooms_levels', []), None, prompt)
        if len(questions) != count:
            raise ValueError('The AI returned an incomplete question-bank expansion. Please retry.')
        for stem, choice, generated_type, generated_mark in zip(questions, choices, types, generated_marks):
            if fingerprint(stem) in used or int(generated_mark) != marks:
                raise ValueError('Expanded bank contains repeated questions or incorrect marks; generation stopped.')
            used.add(fingerprint(stem))
            rows.append({'grade': details['grade'], 'subject': details['subject'], 'board': details['board'],
                'topic': topic, 'question type': qtype, 'marks': marks, 'question': stem, 'options': choice,
                'blooms level': ''})
    output = Path('populated_question_bank.xlsx')
    pd.concat([frame, pd.DataFrame(rows)], ignore_index=True).to_excel(output, index=False)
    return output
