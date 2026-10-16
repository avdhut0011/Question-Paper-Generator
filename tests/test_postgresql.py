"""Opt-in real PostgreSQL migration/locking checks in an isolated temporary schema."""
import os
import uuid
import pytest
from sqlalchemy import create_engine, inspect, text
from flask_migrate import upgrade
from school_platform import create_app, db


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is not configured')
def test_postgresql_migrations_and_skip_locked(tmp_path):
    url=os.environ['TEST_DATABASE_URL']
    if url.startswith('postgresql://'):url=url.replace('postgresql://','postgresql+psycopg://',1)
    assert url.startswith('postgresql+psycopg://'), 'Use a disposable PostgreSQL test database.'
    schema='qpg_test_'+uuid.uuid4().hex
    engine=create_engine(url)
    with engine.begin() as connection:connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        app=create_app({'TESTING':True,'SECRET_KEY':'test-only-secret','SQLALCHEMY_DATABASE_URI':url,
            'SQLALCHEMY_ENGINE_OPTIONS':{'connect_args':{'options':f'-csearch_path={schema}'}},
            'STORAGE_ROOT':str(tmp_path/'private')})
        with app.app_context():
            upgrade()
            assert 'users' in inspect(db.engine).get_table_names()
            from school_platform.models import School, User, GenerationJob
            school=School(name='Test');db.session.add(school);db.session.flush()
            user=User(email='test@example.test',name='Test',role='teacher',school_id=school.id,password_hash='unusable')
            db.session.add(user);db.session.flush()
            first=GenerationJob(user_id=user.id,school_id=school.id,parameters={})
            second=GenerationJob(user_id=user.id,school_id=school.id,parameters={})
            db.session.add_all([first,second]);db.session.commit()
            with db.engine.connect() as a, db.engine.connect() as b:
                txa=a.begin();txb=b.begin()
                one=a.execute(text('SELECT id FROM generation_jobs ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1')).scalar()
                two=b.execute(text('SELECT id FROM generation_jobs ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1')).scalar()
                assert one and two and one!=two
                txa.rollback();txb.rollback()
            db.session.remove();db.engine.dispose()
    finally:
        with engine.begin() as connection:connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
