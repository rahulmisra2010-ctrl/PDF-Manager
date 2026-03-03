from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import bcrypt
from models import db, User, AuditLog
from datetime import datetime

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


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


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            log_action(user.id, 'login', 'User', user.id, f'User {username} logged in')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_action(current_user.id, 'logout', 'User', current_user.id, f'User {current_user.username} logged out')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
