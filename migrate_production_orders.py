"""
Migration script to add ProductionOrder table to the database.
Run this script once to update the database schema.
"""

from app import app, db
from models import ProductionOrder

with app.app_context():
    print("Creating production_orders table...")
    try:
        # Create the production_orders table
        db.create_all()
        print("SUCCESS: ProductionOrder table created successfully!")
        print("\nYou can now use the 'Заказы производство' tab in the dashboard.")
    except Exception as e:
        print(f"ERROR: Error creating table: {e}")
