from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import bcrypt
from models import db, User, AuditLog
from datetime import datetime

user_bp = Blueprint('users', __name__, url_prefix='/users')


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'Admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


def log_action(user_id, action, resource_type, resource_id=None, details=None):
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        details=details,
        timestamp=datetime.utcnow()
    )
    db.session.add(entry)
    db.session.commit()


@user_bp.route('/')
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users/list.html', users=users)


@user_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'Viewer')
        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('users/list.html', users=User.query.all(), show_create=True)
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('users/list.html', users=User.query.all(), show_create=True)
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return render_template('users/list.html', users=User.query.all(), show_create=True)
        if role not in ('Admin', 'Verifier', 'Viewer'):
            role = 'Viewer'
        user = User(
            username=username,
            email=email,
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
            role=role,
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
        log_action(current_user.id, 'create_user', 'User', user.id, f'Created user {username}')
        flash(f'User {username} created.', 'success')
        return redirect(url_for('users.list_users'))
    return redirect(url_for('users.list_users'))


@user_bp.route('/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate yourself.', 'danger')
        return redirect(url_for('users.list_users'))
    user.is_active = not user.is_active
    db.session.commit()
    status = 'activated' if user.is_active else 'deactivated'
    log_action(current_user.id, f'user_{status}', 'User', user_id, f'User {user.username} {status}')
    flash(f'User {user.username} {status}.', 'success')
    return redirect(url_for('users.list_users'))


@user_bp.route('/<int:user_id>/role', methods=['POST'])
@login_required
@admin_required
def change_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role', 'Viewer')
    if new_role not in ('Admin', 'Verifier', 'Viewer'):
        flash('Invalid role.', 'danger')
        return redirect(url_for('users.list_users'))
    old_role = user.role
    user.role = new_role
    db.session.commit()
    log_action(current_user.id, 'change_role', 'User', user_id, f'Changed role from {old_role} to {new_role}')
    flash(f'Role updated to {new_role}.', 'success')
    return redirect(url_for('users.list_users'))


@user_bp.route('/audit-log')
@login_required
@admin_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template('audit/log.html', logs=logs)
