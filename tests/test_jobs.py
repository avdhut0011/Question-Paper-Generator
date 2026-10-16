import copy
import json
import uuid
from conftest import blueprint, login, question, questions, queue, seed_bank
from school_platform import db
from school_platform.jobs import run_next_job
from school_platform.models import Artifact, GenerationJob, Paper, SourceDocument, User


def complete_bank_paper(app,client):
    seed_bank(app);login(client);queue(client)
    with app.app_context():
        assert run_next_job()
        job=db.session.query(GenerationJob).one()
        assert job.status=='completed',job.error
        return job.paper.id


def test_bank_job_approval_and_private_artifacts(app,client):
    paper_id=complete_bank_paper(app,client)
    with app.app_context():
        paper=db.session.get(Paper,paper_id)
        artifacts=[a.id for a in paper.job.artifacts]
        student_html=next(a for a in paper.job.artifacts if a.kind=='html')
        from pathlib import Path
        output=(Path(app.config['STORAGE_ROOT'])/student_html.storage_key).read_text(encoding='utf-8')
        assert 'Correct fraction calculation' not in output
        assert len(artifacts)==3
    assert client.get('/papers/'+paper_id).status_code==200
    assert client.get('/artifacts/'+artifacts[0]).status_code==403
    assert client.post('/papers/'+paper_id+'/submit').status_code==302
    client.post('/logout');login(client,'admin')
    assert client.post('/papers/'+paper_id+'/review',data={'decision':'approved'}).status_code==400
    assert client.post('/papers/'+paper_id+'/review',data={'decision':'approved','checked':'yes'}).status_code==302
    assert client.get('/artifacts/'+artifacts[0]).status_code==200
    client.post('/logout');login(client,'colleague')
    assert client.get('/papers/'+paper_id).status_code==404
    assert client.get('/artifacts/'+artifacts[0]).status_code==404
    client.post('/logout');login(client,'otheradmin')
    assert client.get('/artifacts/'+artifacts[0]).status_code==404


def test_generation_failure_is_recorded(app,client):
    login(client);queue(client)
    with app.app_context():
        run_next_job()
        job=db.session.query(GenerationJob).one()
        assert job.status=='failed'
        assert 'Insufficient approved' in job.error
        assert job.finished_at is not None
        assert db.session.query(Paper).count()==0


def test_revision_preserves_original_and_requires_review(app,client):
    paper_id=complete_bank_paper(app,client)
    response=client.get('/papers/'+paper_id+'/revise')
    assert response.status_code==200
    revised=questions();revised[0]['stem']='Revised question: add one half and one quarter.'
    response=client.post('/papers/'+paper_id+'/revise',data={'request_id':str(uuid.uuid4()),'questions':json.dumps(revised)})
    assert response.status_code==302
    with app.app_context():
        run_next_job()
        original=db.session.get(Paper,paper_id)
        revision=db.session.query(Paper).filter_by(parent_id=paper_id).one()
        assert original.snapshot['questions'][0]['stem']!=revision.snapshot['questions'][0]['stem']
        assert revision.status=='draft'
        revision_id=revision.id
    # A second revision of a bank revision must also work.
    response=client.post('/papers/'+revision_id+'/revise',data={'request_id':str(uuid.uuid4()),'questions':json.dumps(revised)})
    with app.app_context():
        run_next_job()
        assert db.session.query(Paper).count()==3


def test_recent_use_prevents_silent_repetition(app,client):
    complete_bank_paper(app,client);queue(client)
    with app.app_context():
        run_next_job()
        assert db.session.query(GenerationJob).filter_by(status='failed').count()==1


def test_ai_retries_invalid_slot_and_records_usage(app,client,monkeypatch):
    q=question()
    with app.app_context():
        admin=db.session.query(User).filter_by(name='admin').one()
        source=SourceDocument(school_id=admin.school_id,name='Math text',version='edition-1',grade='6',
            subject='Mathematics',board='CBSE',passages={'page-12':q['source_quote']},created_by=admin.id)
        db.session.add(source);db.session.commit();source_id=source.id
    calls=[]
    def generate(slot,passages,previous,error,curriculum):
        assert curriculum['grade']=='6'
        calls.append(error)
        if len(calls)==1:return [],{'input_tokens':10,'output_tokens':2}
        start=1 if slot['type']=='MCQ' else 3
        result=[question(start+i,slot['marks'],slot['type'],slot['difficulty'],slot['bloom']) for i in range(slot['count'])]
        return result,{'input_tokens':30,'output_tokens':50}
    monkeypatch.setattr('school_platform.provider.generate_slot',generate)
    login(client);queue(client,mode='ai',source_id=source_id)
    with app.app_context():
        run_next_job();job=db.session.query(GenerationJob).one()
        assert job.status=='completed',job.error
        assert len(calls)==3 and calls[1]
        assert len(job.paper.snapshot['usage'])==3
        assert job.paper.snapshot['source_version']=='edition-1'


def test_ai_unsupported_citations_fail_after_bounded_attempts(app,client,monkeypatch):
    with app.app_context():
        admin=db.session.query(User).filter_by(name='admin').one()
        source=SourceDocument(school_id=admin.school_id,name='Math text',version='edition-1',grade='6',
            subject='Mathematics',board='CBSE',passages={'different-page':'Some unrelated approved teaching material.'},created_by=admin.id)
        db.session.add(source);db.session.commit();source_id=source.id
    calls=[]
    def generate(*args):
        calls.append(True);return questions()[:2],{}
    monkeypatch.setattr('school_platform.provider.generate_slot',generate)
    login(client);queue(client,mode='ai',source_id=source_id)
    with app.app_context():
        run_next_job();job=db.session.query(GenerationJob).one()
        assert job.status=='failed'
        assert len(calls)==3
        assert db.session.query(Paper).count()==0


def test_pdf_failure_does_not_publish_incomplete_paper(app,client,monkeypatch):
    app.config['REQUIRE_PDF']=True
    seed_bank(app);login(client);queue(client)
    def fail(*args):raise ValueError('PDF rendering failed')
    monkeypatch.setattr('school_platform.rendering.compile_pdf',fail)
    with app.app_context():
        run_next_job()
        assert db.session.query(GenerationJob).one().status=='failed'
        assert db.session.query(Paper).count()==0
        assert db.session.query(Artifact).count()==0


def test_rendered_questions_escape_html(app,client):
    seed_bank(app)
    from school_platform.models import Question
    with app.app_context():
        record=db.session.query(Question).first()
        q=dict(record.content);q['stem']='<script>alert(1)</script> '+q['stem'];record.content=q
        db.session.commit()
    login(client);queue(client)
    with app.app_context():
        run_next_job();paper=db.session.query(Paper).one();paper_id=paper.id
    response=client.get('/papers/'+paper_id)
    assert b'<script>alert(1)</script>' not in response.data
    assert b'&lt;script&gt;' in response.data


def test_artifact_integrity_and_path_traversal(app,client):
    paper_id=complete_bank_paper(app,client)
    with app.app_context():
        paper=db.session.get(Paper,paper_id);paper.status='approved'
        artifact=paper.job.artifacts[0];identifier=artifact.id
        artifact.storage_key='../requirements.txt';db.session.commit()
    assert client.get('/artifacts/'+identifier).status_code==404


def test_self_approval_blocked(app,client):
    seed_bank(app);login(client,'admin');queue(client)
    with app.app_context():
        run_next_job();paper=db.session.query(Paper).one();paper.status='submitted';db.session.commit();paper_id=paper.id
    assert client.post('/papers/'+paper_id+'/review',data={'decision':'approved','checked':'yes'}).status_code==409


def test_review_can_publish_revised_questions_without_duplicate_bank_items(app,client):
    paper_id=complete_bank_paper(app,client)
    revised=questions();revised[0]['stem']='A reviewed replacement fraction question.'
    client.post('/papers/'+paper_id+'/revise',data={'request_id':str(uuid.uuid4()),'questions':json.dumps(revised)})
    with app.app_context():
        run_next_job();revision=db.session.query(Paper).filter_by(parent_id=paper_id).one();revision_id=revision.id
    client.post('/papers/'+revision_id+'/submit');client.post('/logout');login(client,'admin')
    response=client.post('/papers/'+revision_id+'/review',data={'decision':'approved','checked':'yes','publish_questions':'yes'})
    assert response.status_code==302
    from school_platform.models import Question
    with app.app_context():assert db.session.query(Question).count()==5
