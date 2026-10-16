import io
import json
import pytest
from werkzeug.datastructures import FileStorage
from conftest import login, question
from school_platform import db
from school_platform.importing import bank_questions, bank_template, source_passages
from school_platform.models import SourceDocument, Question


def test_reviewed_spreadsheet_template_roundtrip():
    items=bank_questions(FileStorage(stream=bank_template(),filename='questions.xlsx'))
    assert len(items)==1 and items[0]['answer']=='3/4'


def test_json_bank_missing_answer_fails():
    q=question();q.pop('answer')
    with pytest.raises(ValueError):
        bank_questions(FileStorage(stream=io.BytesIO(json.dumps([q]).encode()),filename='bank.json'))


def test_plain_text_source_is_split_into_stable_passages():
    upload=FileStorage(stream=io.BytesIO(b'One approved paragraph.\n\nA second approved paragraph.'),filename='chapter.txt')
    assert list(source_passages(upload))==['passage-1','passage-2']


def test_unreadable_or_wrong_type_source_is_rejected():
    with pytest.raises(ValueError):source_passages(FileStorage(stream=io.BytesIO(b'not a PDF'),filename='chapter.pdf'))
    with pytest.raises(ValueError):source_passages(FileStorage(stream=io.BytesIO(b'content'),filename='chapter.exe'))


def test_admin_can_import_source_and_bank_without_cross_school_publish(app,client):
    login(client,'admin')
    data={'action':'source','grade':'6','subject':'Mathematics','board':'CBSE','name':'Reviewed chapter','version':'v1',
          'content':'One half equals two quarters. Adding one quarter gives three quarters.', 'school_id':'other-school'}
    assert client.post('/admin/library',data=data).status_code==302
    assert client.get('/admin/library/template').status_code==200
    data.update(action='questions',content=json.dumps([question()]))
    assert client.post('/admin/library',data=data).status_code==302
    with app.app_context():
        from school_platform.models import User
        admin=db.session.query(User).filter_by(name='admin').one()
        assert db.session.query(SourceDocument).one().school_id==admin.school_id
        assert db.session.query(Question).one().school_id==admin.school_id


def test_admin_source_upload(app,client):
    login(client,'admin')
    response=client.post('/admin/library',data={'action':'source','grade':'6','subject':'Mathematics','board':'CBSE',
        'name':'Chapter text','version':'v1','content_file':(io.BytesIO(b'One half equals two quarters. This material is reviewed.'),'chapter.txt')},content_type='multipart/form-data')
    assert response.status_code==302
    with app.app_context():assert db.session.query(SourceDocument).one().passages['passage-1'].startswith('One half')
