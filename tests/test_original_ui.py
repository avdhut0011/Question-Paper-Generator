import io
from pathlib import Path
import sys
import types

from conftest import login
from school_platform import db
from school_platform.jobs import run_next_job
from school_platform.models import Artifact, GenerationJob


def test_original_home_and_all_screens_are_restored(client):
    login(client)
    for route, marker in [('/', b'hero-section'), ('/generate_questions', b'question-type-list'),
                          ('/generate_paper', b'useQuestionBank'), ('/upload_question_bank', b'custom_prompt'),
                          ('/chat', b'chat-container')]:
        response = client.get(route)
        assert response.status_code == 200
        assert marker in response.data
        assert b'account.js' in response.data
        assert b'History' in response.data
    assert b'/generate_paper' in client.get('/').data
    assert b'/generate_questions' in client.get('/').data


def test_original_landing_is_public_but_generation_requires_login(client):
    assert b'hero-section' in client.get('/').data
    assert client.get('/generate_paper').status_code == 302
    assert client.get('/generate_questions').status_code == 302
    assert client.get('/history').status_code == 302


def bank_form():
    return {'grade':'6','subject':'Mathematics','board':'CBSE','topic':'Fractions',
        'question_types[]':'MCQ','count_for_type[MCQ]':'2','marks_for_type[MCQ]':'1',
        'export_format':'excel'}


def test_original_bank_form_queues_job_without_replacement_builder(app, client):
    login(client)
    response = client.post('/generate_questions', data=bank_form())
    assert response.status_code == 302 and '/jobs/' in response.headers['Location']
    with app.app_context():
        job = db.session.query(GenerationJob).one()
        assert job.kind == 'original_bank'
        assert job.parameters['blueprint']['num_questions'] == 2


def test_original_form_still_enforces_csrf(app, client):
    login(client)
    app.config['WTF_CSRF_ENABLED'] = True
    page = client.get('/generate_questions')
    assert b'name="csrf_token"' in page.data
    assert client.post('/generate_questions', data=bank_form()).status_code == 400


def test_original_paper_validates_percentages(app, client):
    login(client)
    form = {'grade':'6','subject':'Mathematics','board':'CBSE','total_marks':'10','num_questions':'4',
            'easy_questions':'4','medium_questions':'4','hard_questions':'2'}
    response = client.post('/generate_paper', data=form)
    assert b'must total 100%' in response.data
    form.update(easy_questions='40', medium_questions='40', hard_questions='20')
    assert client.post('/generate_paper', data=form).status_code == 302
    with app.app_context():assert db.session.query(GenerationJob).one().kind == 'original_paper'


def test_original_outputs_use_private_ids_and_ownership(app, client, monkeypatch):
    def generate(**kwargs):
        from openpyxl import Workbook
        path=Path('bank.xlsx');book=Workbook();book.active.append(['Question']);book.active.append(['One draft question'])
        book.save(path);return str(path)
    monkeypatch.setitem(sys.modules,'qg_model',types.SimpleNamespace(generate_question_bank=generate))
    login(client);client.post('/generate_questions',data=bank_form())
    with app.app_context():
        run_next_job();job=db.session.query(GenerationJob).one()
        assert job.status=='completed',job.error
        artifact=db.session.query(Artifact).one();identifier=artifact.id;job_id=job.id
        assert artifact.storage_key.startswith(job_id+'/')
    assert client.get('/jobs/'+job_id+'/preview').status_code==200
    assert client.get('/uploads/'+identifier).status_code==200
    assert client.get('/download/'+identifier).status_code==200
    assert client.get('/uploads/bank.xlsx').status_code==404
    client.post('/logout');login(client,'colleague')
    assert client.get('/uploads/'+identifier).status_code==404
    assert client.get('/jobs/'+job_id+'/preview').status_code==404


def test_original_paper_worker_keeps_html_latex_mode(app,client,monkeypatch):
    def generate(**kwargs):
        Path('paper.tex').write_text('A valid draft')
        return None,'paper.tex','<html><body>Original preview</body></html>',None
    monkeypatch.setitem(sys.modules,'services.paper_service',types.SimpleNamespace(generate_question_paper=generate))
    login(client)
    client.post('/generate_paper',data={'grade':'6','subject':'Mathematics','board':'CBSE',
        'total_marks':'10','num_questions':'4','easy_questions':'40','medium_questions':'40','hard_questions':'20'})
    with app.app_context():
        run_next_job();job=db.session.query(GenerationJob).one();job_id=job.id
        assert job.status=='completed',job.error
        html=db.session.query(Artifact).filter_by(kind='html').one();identifier=html.id
    assert b'Question Paper' in client.get('/jobs/'+job_id+'/preview').data
    assert 'sandbox' in client.get('/uploads/'+identifier).headers['Content-Security-Policy']


def test_chat_upload_is_authenticated_and_retains_original_response_shape(client):
    login(client)
    response=client.post('/api/chat/upload',data={'file':(io.BytesIO(b'A reference about fractions.'),'notes.txt')},content_type='multipart/form-data')
    assert response.status_code==200
    assert response.json['full_content']=='A reference about fractions.'
    assert response.json['status']=='success'


def test_original_generator_creates_excel_and_word(app,tmp_path,monkeypatch):
    import qg_model
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(qg_model,'generate_questions',lambda *args: (
        ['First question [Understand]','Second question [Understand]'],
        ['A) one, B) two, C) three, D) four']*2,['MCQ']*2,[1]*2))
    with app.app_context():
        for export in ('excel','word'):
            path=qg_model.generate_question_bank(grade='6',subject='Mathematics',topic='Fractions',
                question_types=['MCQ'],marks_map={'MCQ':1},count_map={'MCQ':2},num_questions=2,
                board='CBSE',blooms_levels=['Understand'],export_format=export)
            assert path and Path(path).is_file()
            assert Path(path).suffix==('.xlsx' if export=='excel' else '.docx')


def test_original_paper_service_preserves_count_marks_and_math(app,tmp_path,monkeypatch):
    import services.paper_service as paper_service
    monkeypatch.chdir(tmp_path)
    Path('uploads').mkdir()
    monkeypatch.setattr(paper_service,'generate_questions_for_paper',lambda *args:
        'Explain equivalent fractions. [2] [Understand]\nSolve $x + 2 = 5$. [3] [Apply]')
    with app.app_context():
        pdf,tex,html,error=paper_service.generate_question_paper('6','Mathematics',5,
            {'easy':40,'medium':40,'hard':20},2,'CBSE',['Understand','Apply'],'',include_images=False)
        assert error is None,error
        assert pdf is None and Path(tex).is_file() and html
        content=Path(tex).read_text(encoding='utf-8')
        assert 'Error formatting' not in content
        assert '$x + 2 = 5$' in content
        result=paper_service.generate_question_paper('6','Mathematics',6,
            {'easy':40,'medium':40,'hard':20},2,'CBSE',['Understand','Apply'],'',include_images=False)
        assert result[-1] and 'marks' in result[-1]
