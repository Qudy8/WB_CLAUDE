import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration."""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database
    # Fix for Heroku/Render postgres:// vs postgresql://
    database_url = os.environ.get('DATABASE_URL') or 'sqlite:///wb_app.db'
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

    # Encryption
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

    # URL Scheme
    # Force HTTPS URLs in production
    PREFERRED_URL_SCHEME = 'https' if os.environ.get('FLASK_ENV') == 'production' else 'http'

    # Session
    # Allow HTTP in development, require HTTPS in production
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # File uploads
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB max upload size
