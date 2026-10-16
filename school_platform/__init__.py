"""Authenticated school platform. No AI calls or database writes on import."""
import os
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, redirect, request, url_for
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()


def init_platform(app):
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'platform.login'
    login_manager.session_protection = 'strong'
    csrf.init_app(app)
    migrate.init_app(app, db, directory=str(Path(__file__).resolve().parent.parent / 'migrations'))
    from . import models
    from .routes import routes
    from .commands import register_commands
    app.register_blueprint(routes)
    from .original_ui import register_original_ui
    register_original_ui(app)
    register_commands(app)

    @login_manager.user_loader
    def load_user(user_id):
        identifier, _, version = user_id.partition('.')
        user = db.session.get(models.User, identifier)
        return user if user and user.active and str(user.session_version) == version else None

    @app.before_request
    def require_login():
        if request.endpoint in {'static', 'platform.login', 'platform.home', 'index'}:
            return
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if current_user.must_change_password and request.endpoint not in {'platform.password', 'platform.logout'}:
            return redirect(url_for('platform.password'))
        g.user = current_user

    @app.context_processor
    def identity_context():
        return {'current_user': current_user}

    @app.after_request
    def private_responses(response):
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response


def create_app(test_config=None):
    root = Path(__file__).resolve().parent.parent
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    database_url = os.getenv('DATABASE_URL', '')
    if database_url.startswith(('postgres://', 'postgresql://')):
        database_url = 'postgresql+psycopg://' + database_url.split('://', 1)[1]
    app.config.update(
        SECRET_KEY=os.getenv('FLASK_SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        STORAGE_ROOT=str((root / os.getenv('QPG_STORAGE_ROOT', 'instance/private')).resolve()),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('QPG_HTTPS', 'true').lower() == 'true',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,
        GEMINI_MODEL=os.getenv('GEMINI_MODEL', ''),
        GEMINI_API_KEY=os.getenv('GEMINI_API_KEY_PRO') or os.getenv('GEMINI_API_KEY'),
        REQUIRE_PDF=os.getenv('QPG_REQUIRE_PDF', 'true').lower() == 'true',
    )
    if test_config:
        app.config.update(test_config)
    if not app.config['SECRET_KEY'] or app.config['SECRET_KEY'] in {'supersecretkey', 'your_secret_key_here', 'replace_with_a_unique_random_secret'}:
        raise RuntimeError('Set FLASK_SECRET_KEY to a unique random secret before starting the platform.')
    if not app.config['TESTING'] and len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('FLASK_SECRET_KEY must contain at least 32 characters in production.')
    if not app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError('Set DATABASE_URL in .env. See README.md for PostgreSQL setup.')
    if not app.config['TESTING'] and not app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
        raise RuntimeError('The school platform requires PostgreSQL.')
    Path(app.config['STORAGE_ROOT']).mkdir(parents=True, exist_ok=True)
    init_platform(app)
    return app
