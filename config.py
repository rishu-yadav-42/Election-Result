import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, 'database')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

os.makedirs(DATABASE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'change_this_secret')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(
        DATABASE_DIR, os.getenv('DATABASE_NAME', 'database.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = UPLOAD_DIR
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
