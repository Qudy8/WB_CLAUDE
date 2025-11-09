"""
Migration script to add label settings columns to User table.

This script adds new boolean columns to the users table for controlling
what fields are displayed on product labels during production.

Run this script once after updating models.py:
    python migrate_label_settings.py
"""

from app import app
from models import db
import sqlite3

def migrate():
    """Add label settings columns to users table."""

    with app.app_context():
        # Get database path from config
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')

        print(f"Migrating database: {db_path}")

        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # List of new columns to add
        new_columns = [
            ('label_show_ean', 'INTEGER', 1),
            ('label_show_gs1', 'INTEGER', 1),
            ('label_show_title', 'INTEGER', 1),
            ('label_show_color', 'INTEGER', 1),
            ('label_show_size', 'INTEGER', 1),
            ('label_show_material', 'INTEGER', 1),
            ('label_show_country', 'INTEGER', 1),
            ('label_show_ip', 'INTEGER', 1),
            ('label_show_article', 'INTEGER', 1),
        ]

        # Check which columns already exist
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        # Add missing columns
        for col_name, col_type, default_value in new_columns:
            if col_name not in existing_columns:
                print(f"Adding column: {col_name}")
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type} DEFAULT {default_value}")
            else:
                print(f"Column already exists: {col_name}")

        # Commit changes
        conn.commit()
        conn.close()

        print("\nMigration completed successfully!")
        print("All label settings columns have been added to the users table.")
        print("Default values: all settings are enabled (True/1) by default.")

if __name__ == '__main__':
    migrate()
