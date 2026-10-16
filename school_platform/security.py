from functools import wraps
from pathlib import Path

from flask import abort, current_app
from flask_login import current_user
from sqlalchemy import false
from . import db
from .models import AuditEvent, TeachingAssignment


def audit(action, target=None, **details):
    db.session.add(AuditEvent(user_id=current_user.id if current_user.is_authenticated else None,
                              action=action, target_id=target, details=details))


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if current_user.role not in {'group_admin', 'school_admin'}:
            abort(403)
        return fn(*args, **kwargs)
    return wrapped


def scope(query, model):
    if current_user.role == 'group_admin':
        return query
    if current_user.role == 'school_admin':
        return query.filter(model.school_id == current_user.school_id)
    if hasattr(model, 'user_id'):
        return query.filter(model.user_id == current_user.id, model.school_id == current_user.school_id)
    return query.filter(model.school_id == current_user.school_id)


def may_teach(user, grade, subject, board):
    if user.role != 'teacher':
        return True
    return db.session.query(TeachingAssignment.id).filter_by(
        user_id=user.id, grade=grade, subject=subject, board=board).first() is not None


def private_path(key):
    root = Path(current_app.config['STORAGE_ROOT']).resolve()
    candidate = (root / key).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        abort(404)
    return candidate
