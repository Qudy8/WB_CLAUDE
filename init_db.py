"""Initialize database with all tables."""
from app import app, db

with app.app_context():
    db.create_all()
    print("Database initialized with all tables including new label settings fields!")
