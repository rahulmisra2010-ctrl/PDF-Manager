import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect

from config import Config
from models import db, User, AuditLog

login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

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
        _create_default_admin(app)

    return app


def _create_default_admin(app):
    if not User.query.filter_by(role='Admin').first():
        admin = User(
            username='admin',
            email='admin@pdfmanager.local',
            password_hash=bcrypt.generate_password_hash('admin123').decode('utf-8'),
            role='Admin',
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print('Default admin created: admin / admin123')


if __name__ == '__main__':
    app = create_app()
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=5000)
