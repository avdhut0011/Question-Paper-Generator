"""Provision this local PostgreSQL application without retaining admin credentials."""
import getpass
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import dotenv_values
    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import make_url

    settings = dotenv_values(ROOT / '.env')
    url = make_url(settings['DATABASE_URL'])
    if url.host not in {'localhost', '127.0.0.1'}:
        raise RuntimeError('Local provisioning only supports localhost. Configure a remote database separately.')
    if not url.username or not url.database or not url.password:
        raise RuntimeError('DATABASE_URL must include the dedicated application username, password, and database.')
    password = getpass.getpass('Local PostgreSQL postgres password: ')
    with psycopg.connect(host=url.host, port=url.port or 5432, dbname='postgres',
                        user='postgres', password=password, autocommit=True) as connection:
        role_exists = connection.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (url.username,)).fetchone()
        database = connection.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s',
                                      (url.database,)).fetchone()
        if database and database[0] != url.username:
            raise RuntimeError('The target database belongs to another role. No changes were made.')
        if not role_exists:
            connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}')
                               .format(sql.Identifier(url.username), sql.Literal(url.password)))
        # Existing roles are never reset. Verify the configured password before proceeding.
        if not database:
            if role_exists:
                with psycopg.connect(host=url.host, port=url.port or 5432, dbname='postgres',
                                     user=url.username, password=url.password):
                    pass
            connection.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(
                sql.Identifier(url.database), sql.Identifier(url.username)))
    del password
    print('Dedicated PostgreSQL account and database verified.')

    for key, value in settings.items():
        if value is not None:
            os.environ[key] = value
    from school_platform import create_app, db
    from school_platform.models import AuditEvent, School, User
    from sqlalchemy import inspect
    from flask_migrate import upgrade

    app = create_app()
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
        expected = set(db.metadata.tables) | {'alembic_version'}
        if tables - expected or tables and 'alembic_version' not in tables:
            raise RuntimeError('Target database has an unmanaged schema. Inspect it before applying migrations.')
        upgrade()
        print('Database migrations applied.')
        if not db.session.query(User.id).filter_by(role='group_admin').first():
            school = db.session.query(School).filter_by(name='Ashoka Group of Schools').first()
            if not school:
                school = School(name='Ashoka Group of Schools')
                db.session.add(school)
                db.session.flush()
            temporary_password = secrets.token_urlsafe(20)
            user = User(email='admin@ashoka.local', name='Ashoka Administrator', role='group_admin',
                        school_id=school.id, must_change_password=True)
            user.set_password(temporary_password)
            db.session.add(user)
            db.session.flush()
            db.session.add(AuditEvent(user_id=user.id, action='admin.bootstrap', target_id=user.id))
            credentials = ROOT / 'instance' / 'INITIAL_ADMIN.txt'
            credentials.parent.mkdir(parents=True, exist_ok=True)
            credentials.write_text('Local administrator login\nEmail: admin@ashoka.local\nTemporary password: '
                                   + temporary_password + '\nChange this password on first sign-in.\n', encoding='utf-8')
            db.session.commit()
            print('Initial administrator created. Credentials: instance/INITIAL_ADMIN.txt')
        else:
            print('Existing administrator preserved.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not print connection URLs or exception messages that may contain credentials.
        print(f'Local setup failed ({type(exc).__name__}). No existing passwords were reset.', file=sys.stderr)
        raise SystemExit(1)
