import json
import re
from conftest import PASSWORD, login, queue, blueprint
from school_platform import db
from school_platform.models import GenerationJob, LoginAttempt, TeachingAssignment, User


def test_login_required_and_anonymous_file_routes_removed(client):
    for path in ['/history','/papers/new','/admin','/uploads/anything','/download/anything']:
        assert client.get(path).status_code==302
    assert client.get('/login').status_code==200
    login(client)
    assert client.get('/uploads/anything').status_code==404
    assert client.get('/download/anything').status_code==404
    assert client.get('/open_file/anything').status_code==404


def test_teacher_cannot_manage_staff(client):
    login(client)
    assert client.get('/admin').status_code==403
    assert client.get('/admin/library').status_code==403
    assert client.post('/admin',data={'action':'school','name':'Evil'}).status_code==403


def test_teacher_needs_matching_assignment(client):
    login(client)
    b=blueprint();b['subject']='Physics'
    assert queue(client,blueprint=json.dumps(b)).status_code==403


def test_school_scope_and_teacher_ownership(app,client):
    login(client)
    response=queue(client);url=response.headers['Location']
    assert client.get(url).status_code==200
    for user,expected in [('colleague',404),('outsider',404),('admin',200),('otheradmin',404),('group',200)]:
        client.post('/logout');login(client,user)
        assert client.get(url).status_code==expected


def test_staff_account_requires_password_change(app,client):
    with app.app_context():
        db.session.query(User).filter_by(name='teacher').one().must_change_password=True;db.session.commit()
    login(client)
    assert client.get('/history').headers['Location'].endswith('/password')
    assert client.post('/password',data={'current_password':PASSWORD,'password':'New-password-12345','confirm_password':'New-password-12345'}).status_code==302
    assert client.get('/history').status_code==200


def test_password_reset_revokes_session(app,client):
    login(client)
    second=app.test_client();login(second,'admin')
    with app.app_context():uid=db.session.query(User).filter_by(name='teacher').one().id
    assert second.post('/admin',data={'action':'reset_password','user_id':uid,'password':'Reset-password-12345'}).status_code==302
    assert client.get('/history').status_code==302


def test_admin_cannot_manage_other_school(app,client):
    login(client,'admin')
    with app.app_context():uid=db.session.query(User).filter_by(name='outsider').one().id
    assert client.post('/admin',data={'action':'toggle_user','user_id':uid}).status_code==404
    assert client.post('/admin',data={'action':'user','role':'group_admin'}).status_code==403


def test_csrf_blocks_missing_and_accepts_valid_token(app,client):
    app.config['WTF_CSRF_ENABLED']=True
    assert client.post('/login',data={'email':'teacher@school.test','password':PASSWORD}).status_code==400
    response=client.get('/login')
    token=re.search(rb'name="csrf_token" value="([^"]+)"',response.data).group(1).decode()
    assert client.post('/login',data={'email':'teacher@school.test','password':PASSWORD,'csrf_token':token}).status_code==302
    assert client.post('/logout').status_code==400


def test_login_lockout(app,client):
    for _ in range(5):
        assert client.post('/login',data={'email':'teacher@school.test','password':'wrong'}).status_code==401
    assert login(client).status_code==401


def test_duplicate_submission_and_quota(app,client):
    login(client)
    import uuid
    identifier=str(uuid.uuid4())
    a=queue(client,request_id=identifier);b=queue(client,request_id=identifier)
    assert a.headers['Location']==b.headers['Location']
    queue(client);queue(client)
    assert b'Generation limit reached' in queue(client).data
    with app.app_context():assert db.session.query(GenerationJob).count()==3


def test_cancel_and_history_filters(app,client):
    login(client);response=queue(client);url=response.headers['Location']
    assert client.post(url+'/cancel').status_code==302
    assert b'cancelled' in client.get('/history?status=cancelled&subject=Mathematics').data
    assert b'No generation attempts' in client.get('/history?subject=Physics').data


def test_template_pages_render_for_admin(client):
    login(client,'admin')
    for path in ['/admin','/admin/library','/admin/audit','/papers/new','/password']:
        assert client.get(path).status_code==200
