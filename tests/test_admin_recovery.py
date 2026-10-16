from datetime import timedelta

from conftest import PASSWORD, login
from school_platform import db
from school_platform.models import AuditEvent, User, utcnow


def test_console_recovery_revokes_sessions_and_allows_new_login(app, client):
    login(client, 'group')
    with app.app_context():
        user = db.session.query(User).filter_by(name='group').one()
        user.failed_logins = 6
        user.locked_until = utcnow() + timedelta(minutes=15)
        db.session.commit()
    password = 'Recovered-admin-password-123'
    result = app.test_cli_runner().invoke(args=['reset-admin-password', '--email', 'GROUP@school.test'],
                                          input=password + '\n' + password + '\n')
    assert result.exit_code == 0
    assert password not in result.output
    assert client.get('/admin').status_code == 302
    assert client.post('/login', data={'email': 'group@school.test', 'password': PASSWORD}).status_code == 401
    assert client.post('/login', data={'email': 'group@school.test', 'password': password}).status_code == 302
    assert client.get('/admin').status_code == 200
    with app.app_context():
        assert db.session.query(AuditEvent).filter_by(action='admin.password_recovered').count() == 1


def test_console_recovery_rejects_short_password_and_non_admin(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=['reset-admin-password', '--email', 'group@school.test'], input='short\nshort\n')
    assert result.exit_code != 0
    with app.app_context():
        assert db.session.query(User).filter_by(name='group').one().check_password(PASSWORD)
    for email in ('teacher@school.test', 'missing@school.test'):
        result = runner.invoke(args=['reset-admin-password', '--email', email])
        assert result.exit_code != 0
        assert 'No active administrator' in result.output


def test_console_recovery_cannot_reactivate_account_or_accept_password_in_argv(app):
    with app.app_context():
        user = db.session.query(User).filter_by(name='group').one()
        user.active = False
        db.session.commit()
    runner = app.test_cli_runner()
    result = runner.invoke(args=['reset-admin-password', '--email', 'group@school.test'])
    assert result.exit_code != 0
    result = runner.invoke(args=['reset-admin-password', '--email', 'admin@school.test', '--password', 'example'])
    assert result.exit_code != 0
    assert 'No such option' in result.output
