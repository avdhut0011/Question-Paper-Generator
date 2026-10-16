import copy
import json
import uuid
from pathlib import Path

import pytest
from school_platform import create_app, db
from school_platform.models import School, TeachingAssignment, User
from school_platform.routes import DEFAULT_BLUEPRINT

PASSWORD = 'Staff-test-password-123'


@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only-secret',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'test.sqlite'),
        'STORAGE_ROOT': str(tmp_path / 'private'), 'WTF_CSRF_ENABLED': False,
        'SESSION_COOKIE_SECURE': False, 'REQUIRE_PDF': False})
    with app.app_context():
        db.create_all()
        a, b = School(name='Ashoka A'), School(name='Ashoka B')
        db.session.add_all([a, b]); db.session.flush()
        for name, role, school in [('teacher', 'teacher', a), ('colleague', 'teacher', a),
                                   ('outsider', 'teacher', b), ('admin', 'school_admin', a),
                                   ('otheradmin', 'school_admin', b), ('group', 'group_admin', a)]:
            user = User(email=name+'@school.test', name=name, role=role, school_id=school.id, must_change_password=False)
            user.set_password(PASSWORD)
            db.session.add(user); db.session.flush()
            db.session.add(TeachingAssignment(user_id=user.id, grade='6', subject='Mathematics', board='CBSE'))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, name='teacher'):
    return client.post('/login', data={'email':name+'@school.test', 'password':PASSWORD})


def question(index=0, marks=1, qtype='MCQ', difficulty='easy', bloom='Understand'):
    return {'stem':f'Question {index}: what is one half plus one quarter?', 'type':qtype,
        'marks':marks, 'chapter':'Fractions', 'difficulty':difficulty, 'bloom':bloom,
        'options':['1/4','1/2','3/4','1'] if qtype == 'MCQ' else [],
        'answer':'3/4', 'solution':'One half equals two quarters; add one quarter.',
        'rubric':[{'criterion':'Correct fraction calculation', 'marks':marks}],
        'source_reference':'page-12', 'source_quote':'One half equals two quarters. Adding one quarter gives three quarters.'}


def questions():
    return [question(1),question(2),question(3,4,'Short Answer','medium','Apply'),question(4,4,'Short Answer','medium','Apply')]


def blueprint():
    return copy.deepcopy(DEFAULT_BLUEPRINT)


def queue(client, **overrides):
    data={'request_id':str(uuid.uuid4()), 'mode':'bank', 'blueprint':json.dumps(blueprint())}
    data.update(overrides)
    return client.post('/papers/new',data=data)


def seed_bank(app):
    from school_platform.models import Question
    with app.app_context():
        user=db.session.query(User).filter_by(name='admin').one()
        for content in questions():
            db.session.add(Question(school_id=user.school_id, grade='6',subject='Mathematics',board='CBSE',
                                    content=content,approved=True,created_by=user.id))
        db.session.commit()
