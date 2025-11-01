"""
Migration script to add sizes_defect_json column to finished_goods_stock table.
Run this script once to update the database schema.
"""

from app import app, db
from models import FinishedGoodsStock
from sqlalchemy import text

with app.app_context():
    print("Adding sizes_defect_json column to finished_goods_stock table...")
    try:
        # Check if column already exists
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('finished_goods_stock')]

        if 'sizes_defect_json' not in columns:
            # Add the column using raw SQL
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE finished_goods_stock ADD COLUMN sizes_defect_json TEXT'))
                conn.commit()
            print("SUCCESS: sizes_defect_json column added successfully!")
        else:
            print("INFO: sizes_defect_json column already exists, skipping...")

        print("\nYou can now use the Defects tracking feature in the dashboard.")
        print("Defect quantities are now stored together with finished goods stock.")
    except Exception as e:
        print(f"ERROR: Error updating table: {e}")
