"""Force initialize database with proper model imports."""
import os

# Remove old database if exists
db_paths = ['wb_app.db', 'instance/wb_app.db']
for db_path in db_paths:
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f'Removed old database: {db_path}')

from app import app
from models import db, User, Session, SessionMember, ProductGroup, Product, Order, OrderItem
from models import ProductionItem, CISLabel, Box, BoxItem, Delivery, DeliveryBox
from models import PrintTask, Inventory, FinishedGoodsStock, Defect

print('All models imported')

with app.app_context():
    print('Creating all tables...')
    db.create_all()
    print('Tables created successfully!')

# Verify
import sqlite3
# Get actual database path from app
db_file_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
if not os.path.isabs(db_file_path):
    # Relative path - Flask creates it in instance folder
    db_file_path = os.path.join('instance', db_file_path)
print(f'\nChecking database at: {db_file_path}')
conn = sqlite3.connect(db_file_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print(f'\nTables in database ({len(tables)}):')
for table in tables:
    print(f'  - {table[0]}')

# Check users table
cursor.execute("PRAGMA table_info(users)")
columns = cursor.fetchall()
print(f'\nUser table has {len(columns)} columns')

# Check for label settings columns
label_cols = [c[1] for c in columns if c[1].startswith('label_show_')]
print(f'\nLabel settings columns ({len(label_cols)}):')
for col in label_cols:
    print(f'  - {col}')

conn.close()
