"""Database migration script to add missing columns and tables."""
import sqlite3
import os

# Path to database
db_path = os.path.join('instance', 'wb_app.db')

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Starting database migration...")

# Check if film_usage column exists in print_tasks
try:
    cursor.execute("SELECT film_usage FROM print_tasks LIMIT 1")
    print("[OK] Column 'film_usage' already exists in print_tasks")
except sqlite3.OperationalError:
    print("Adding 'film_usage' column to print_tasks...")
    cursor.execute("ALTER TABLE print_tasks ADD COLUMN film_usage REAL DEFAULT 0.0")
    print("[OK] Added 'film_usage' column to print_tasks")

# Check if inventory table exists
try:
    cursor.execute("SELECT * FROM inventory LIMIT 1")
    print("[OK] Table 'inventory' already exists")
except sqlite3.OperationalError:
    print("Creating 'inventory' table...")
    cursor.execute("""
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            boxes_60x40x40 INTEGER DEFAULT 0,
            bags_25x30 INTEGER DEFAULT 0,
            print_film INTEGER DEFAULT 0,
            paint_white INTEGER DEFAULT 0,
            paint_black INTEGER DEFAULT 0,
            paint_red INTEGER DEFAULT 0,
            paint_yellow INTEGER DEFAULT 0,
            paint_blue INTEGER DEFAULT 0,
            glue INTEGER DEFAULT 0,
            label_rolls INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    print("[OK] Created 'inventory' table")

# Check if finished_goods_stock table exists
try:
    cursor.execute("SELECT * FROM finished_goods_stock LIMIT 1")
    print("[OK] Table 'finished_goods_stock' already exists")
except sqlite3.OperationalError:
    print("Creating 'finished_goods_stock' table...")
    cursor.execute("""
        CREATE TABLE finished_goods_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            color TEXT,
            sizes_stock_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    print("[OK] Created 'finished_goods_stock' table")

# Check if color column exists in finished_goods_stock
try:
    cursor.execute("SELECT color FROM finished_goods_stock LIMIT 1")
    print("[OK] Column 'color' already exists in finished_goods_stock")
except sqlite3.OperationalError:
    print("Adding 'color' column to finished_goods_stock...")
    cursor.execute("ALTER TABLE finished_goods_stock ADD COLUMN color TEXT")
    print("[OK] Added 'color' column to finished_goods_stock")

# Commit changes
conn.commit()
conn.close()

print("\nMigration completed successfully!")
