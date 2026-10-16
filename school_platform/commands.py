import time
from datetime import timedelta
import click
from flask.cli import with_appcontext
from sqlalchemy import select
from . import db
from .models import AuditEvent, GenerationJob, LoginAttempt, School, User, utcnow


def register_commands(app):
    @app.cli.command('reset-admin-password')
    @click.option('--email', prompt='Administrator email')
    def reset_admin_password(email):
        """Recover an active administrator using trusted local console access."""
        user = db.session.query(User).filter_by(email=email.strip().casefold()).one_or_none()
        if not user or not user.active or user.role not in {'group_admin', 'school_admin'}:
            raise click.ClickException('No active administrator matches that email.')
        password = click.prompt('New password (at least 12 characters)', hide_input=True,
                                confirmation_prompt=True)
        try:
            user.set_password(password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        user.must_change_password = False
        user.session_version += 1
        user.failed_logins = 0
        user.locked_until = None
        db.session.add(AuditEvent(user_id=user.id, action='admin.password_recovered', target_id=user.id,
                                 details={'method': 'local_console'}))
        db.session.commit()
        click.echo('Administrator password reset. Previous sessions have been signed out.')

    @app.cli.command('prune-login-attempts')
    def prune_login_attempts():
        """Remove expired rate-limit counters without deleting the audit trail."""
        count = db.session.query(LoginAttempt).filter(LoginAttempt.created_at < utcnow() - timedelta(days=1)).delete()
        db.session.commit()
        click.echo(f'Removed {count} expired login counters.')

    @app.cli.command('bootstrap-admin')
    @click.option('--email', prompt=True)
    @click.option('--name', prompt=True)
    @click.option('--school', prompt=True)
    @click.password_option(confirmation_prompt=True)
    def bootstrap_admin(email, name, school, password):
        """Create the first group administrator. Never accepts passwords in argv."""
        if db.session.query(User.id).filter_by(role='group_admin').first():
            raise click.ClickException('A group administrator already exists. Use the admin page to manage staff.')
        school_record = School(name=school.strip())
        db.session.add(school_record)
        db.session.flush()
        user = User(email=email.strip().casefold(), name=name.strip(), role='group_admin',
                    school_id=school_record.id, must_change_password=False)
        try:
            user.set_password(password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        db.session.add(user)
        db.session.flush()
        db.session.add(AuditEvent(user_id=user.id, action='admin.bootstrap', target_id=user.id))
        db.session.commit()
        click.echo('Group administrator created.')

    @app.cli.command('worker')
    @click.option('--once', is_flag=True, help='Process one queued job and exit.')
    def worker(once):
        """Process durable paper-generation jobs; run separately from the web server."""
        from .jobs import run_next_job
        while True:
            processed = run_next_job()
            db.session.remove()
            if once:
                break
            if not processed:
                time.sleep(2)

    @app.cli.command('recover-jobs')
    @click.option('--older-than-minutes', default=120, type=click.IntRange(30))
    def recover_jobs(older_than_minutes):
        """Fail abandoned running jobs after stopping workers; do not silently duplicate work."""
        cutoff = utcnow() - timedelta(minutes=older_than_minutes)
        jobs = db.session.execute(select(GenerationJob).where(
            GenerationJob.status == 'running', GenerationJob.started_at < cutoff).with_for_update()).scalars().all()
        for job in jobs:
            job.status, job.error, job.finished_at = 'failed', 'Worker interrupted. Create a new generation attempt.', utcnow()
            db.session.add(AuditEvent(action='generation.recovered', target_id=job.id))
        db.session.commit()
        click.echo(f'Marked {len(jobs)} abandoned jobs failed.')
