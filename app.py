import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect

from config import Config
from models.models import db, User, State
from werkzeug.security import generate_password_hash

csrf = CSRFProtect()

# States / UTs offered when creating an election ("India" is used for national Lok Sabha uploads)
INDIAN_STATES = [
    'India', 'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
    'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala',
    'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland',
    'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
    'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
    'Andaman and Nicobar Islands', 'Chandigarh', 'Dadra and Nagar Haveli and Daman and Diu',
    'Delhi', 'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
]


def seed_database(app):
    """Create tables, default admin user and state list. No election data is seeded -
    every dashboard only exists after the Admin uploads a dataset."""
    with app.app_context():
        db.create_all()

        admin_username = os.getenv('ADMIN_USERNAME', 'admin')
        admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
        if not User.query.filter_by(username=admin_username).first():
            db.session.add(User(
                username=admin_username,
                password_hash=generate_password_hash(admin_password),
                role='admin',
            ))

        existing = {s.name for s in State.query.all()}
        for name in INDIAN_STATES:
            if name not in existing:
                db.session.add(State(name=name))

        db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    csrf.init_app(app)

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.dashboard import dashboard_bp
    from routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)

    seed_database(app)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', code=403,
                               message='You do not have permission to access this page.'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', code=404,
                               message='The page or election you are looking for does not exist.'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('error.html', code=500,
                               message='Something went wrong on our side. Please try again later.'), 500

    return app


app = create_app()

if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(host='127.0.0.1', port=5000, debug=debug)
