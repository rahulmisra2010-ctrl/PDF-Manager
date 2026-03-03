import os
import secrets
from flask import Flask, redirect, url_for
from extensions import bcrypt, login_manager, csrf
from config import Config
from models import db, User, AuditLog


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Warn if using default secret key
    if app.config['SECRET_KEY'] == 'dev-secret-key-change-in-prod':
        app.logger.warning('WARNING: Using default SECRET_KEY. Set SECRET_KEY env var in production.')

    # Ensure upload/export dirs exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from routes.auth_routes import auth_bp
    from routes.pdf_routes import pdf_bp
    from routes.dashboard_routes import dashboard_bp
    from routes.search_routes import search_bp
    from routes.user_routes import user_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pdf_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(user_bp)

    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))

    # Create tables and default admin
    with app.app_context():
        db.create_all()
        _create_default_admin()

    return app


def _create_default_admin():
    if not User.query.filter_by(role='Admin').first():
        # Use env var password or generate a random one
        password = os.environ.get('ADMIN_PASSWORD') or secrets.token_urlsafe(12)
        admin = User(
            username='admin',
            email='admin@pdfmanager.local',
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
            role='Admin',
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print(f'Default admin created. Username: admin  Password: {password}')


if __name__ == '__main__':
    _app = create_app()
    _debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    _app.run(debug=_debug, host='0.0.0.0', port=5000)
