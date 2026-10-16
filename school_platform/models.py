import uuid
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from . import db


def identifier():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class School(db.Model):
    __tablename__ = 'schools'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    name = db.Column(db.String(160), nullable=False, unique=True)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    email = db.Column(db.String(254), nullable=False, unique=True)
    name = db.Column(db.String(160), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='teacher')
    school_id = db.Column(db.String(36), db.ForeignKey('schools.id'), nullable=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    locked_until = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    school = db.relationship(School)
    __table_args__ = (db.CheckConstraint("role IN ('teacher', 'school_admin', 'group_admin')", name='valid_user_role'),)

    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        if len(password) < 12:
            raise ValueError('Use a password with at least 12 characters.')
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f'{self.id}.{self.session_version}'


class LoginAttempt(db.Model):
    __tablename__ = 'login_attempts'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    address_hash = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class TeachingAssignment(db.Model):
    __tablename__ = 'teaching_assignments'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    grade = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    board = db.Column(db.String(50), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'grade', 'subject', 'board', name='unique_assignment'),)


class SourceDocument(db.Model):
    __tablename__ = 'source_documents'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    school_id = db.Column(db.String(36), db.ForeignKey('schools.id'), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    version = db.Column(db.String(80), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    board = db.Column(db.String(50), nullable=False)
    # Immutable approved text passages keyed by stable page/paragraph reference.
    passages = db.Column(db.JSON, nullable=False)
    created_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint('school_id', 'name', 'version', 'grade', 'subject', 'board',
                                        name='unique_source_version'),)


class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    school_id = db.Column(db.String(36), db.ForeignKey('schools.id'), nullable=False, index=True)
    grade = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    board = db.Column(db.String(50), nullable=False)
    content = db.Column(db.JSON, nullable=False)
    approved = db.Column(db.Boolean, nullable=False, default=False)
    created_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class GenerationJob(db.Model):
    __tablename__ = 'generation_jobs'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    school_id = db.Column(db.String(36), db.ForeignKey('schools.id'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False, default='paper')
    status = db.Column(db.String(20), nullable=False, default='queued', index=True)
    parameters = db.Column(db.JSON, nullable=False)
    metrics = db.Column(db.JSON, nullable=False, default=dict)
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    started_at = db.Column(db.DateTime(timezone=True))
    finished_at = db.Column(db.DateTime(timezone=True))
    user = db.relationship(User)
    school = db.relationship(School)
    __table_args__ = (db.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name='valid_job_status'),)


class Paper(db.Model):
    __tablename__ = 'papers'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    job_id = db.Column(db.String(36), db.ForeignKey('generation_jobs.id'), nullable=False, unique=True)
    school_id = db.Column(db.String(36), db.ForeignKey('schools.id'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    # Each revision is a new immutable paper row; never overwrite an approved snapshot.
    parent_id = db.Column(db.String(36), db.ForeignKey('papers.id'))
    status = db.Column(db.String(20), nullable=False, default='draft')
    snapshot = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    reviewed_by = db.Column(db.String(36), db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    review_note = db.Column(db.Text)
    job = db.relationship(GenerationJob, backref=db.backref('paper', uselist=False))
    __table_args__ = (db.CheckConstraint("status IN ('draft', 'submitted', 'approved', 'rejected')", name='valid_paper_status'),)


class Artifact(db.Model):
    __tablename__ = 'artifacts'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    job_id = db.Column(db.String(36), db.ForeignKey('generation_jobs.id'), nullable=False, index=True)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(30), nullable=False)
    checksum = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    job = db.relationship(GenerationJob, backref='artifacts')


class AuditEvent(db.Model):
    __tablename__ = 'audit_events'
    id = db.Column(db.String(36), primary_key=True, default=identifier)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    action = db.Column(db.String(80), nullable=False)
    target_id = db.Column(db.String(36))
    details = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
