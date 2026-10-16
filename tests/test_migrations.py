from pathlib import Path
from sqlalchemy import inspect
from flask_migrate import upgrade, downgrade
from school_platform import create_app, db


def test_initial_migration_roundtrip(tmp_path):
    app=create_app({'TESTING':True,'SECRET_KEY':'test-only-secret','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'migration.sqlite'),
                    'STORAGE_ROOT':str(tmp_path/'private')})
    with app.app_context():
        upgrade()
        assert set(db.metadata.tables) <= set(inspect(db.engine).get_table_names())
        downgrade(revision='base')
        assert 'users' not in inspect(db.engine).get_table_names()
        upgrade()
        assert 'papers' in inspect(db.engine).get_table_names()
        db.session.remove();db.engine.dispose()


def test_bootstrap_admin_is_one_time(app):
    runner=app.test_cli_runner()
    result=runner.invoke(args=['bootstrap-admin','--email','new@school.test','--name','New','--school','New school'],input='Strong-password-12345\nStrong-password-12345\n')
    assert result.exit_code!=0
    assert 'already exists' in result.output
