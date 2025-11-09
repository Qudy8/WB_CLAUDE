"""Check database status."""
from app import app, db
from models import User, Session
import os
import sqlite3

print('Models imported successfully')
print('Database URI:', app.config.get('SQLALCHEMY_DATABASE_URI'))

with app.app_context():
    print('Creating tables...')
    db.create_all()
    print('Tables created')

print('Database file exists:', os.path.exists('wb_app.db'))
print('Database file size:', os.path.getsize('wb_app.db') if os.path.exists('wb_app.db') else 0)

# Check tables
conn = sqlite3.connect('wb_app.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('\nTables in database:', [t[0] for t in tables])

if 'users' in [t[0] for t in tables]:
    cursor.execute("PRAGMA table_info(users)")
    columns = cursor.fetchall()
    print('\nUser table columns:')
    for col in columns:
        print(f'  - {col[1]} ({col[2]})')

    # Check for label settings columns
    label_cols = [c[1] for c in columns if c[1].startswith('label_show_')]
    print('\nLabel settings columns found:', label_cols)

conn.close()
