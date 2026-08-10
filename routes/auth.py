"""Authentication routes: secure Admin login with hashed passwords and sessions."""

from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import check_password_hash

from models.models import User

auth_bp = Blueprint('auth', __name__)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('admin_logged_in'):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('login.html'), 400

        user = User.query.filter_by(username=username, role='admin').first()
        if user and check_password_hash(user.password_hash, password):
            session['admin_logged_in'] = True
            session['admin_username'] = user.username
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('admin.dashboard'))

        flash('Invalid username or password.', 'danger')
        return render_template('login.html'), 401

    return render_template('login.html')


@auth_bp.route('/admin/logout')
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    session.pop('upload_staging', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('dashboard.index'))
