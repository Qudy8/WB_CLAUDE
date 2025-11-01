"""
Migration script to add Defect table to the database.
Run this script once to update the database schema.
"""

from app import app, db
from models import Defect

with app.app_context():
    print("Creating defects table...")
    try:
        # Create the defects table
        db.create_all()
        print("SUCCESS: Defects table created successfully!")
        print("\nYou can now use the Defects tab in the dashboard.")
    except Exception as e:
        print(f"ERROR: Error creating table: {e}")
