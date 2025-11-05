"""
Migration script to add wb_api_key_hash column to product_groups and orders tables.

This allows tracking which WB cabinet (API key) was used to create each entity,
enabling multi-cabinet workflow where users can only edit data from their own cabinet.

Usage:
    python migrate_add_wb_cabinet_hash.py
"""

from app import app, db
from models import ProductGroup, Order
from sqlalchemy import text


def migrate():
    """Add wb_api_key_hash column to product_groups and orders tables."""
    with app.app_context():
        print("Starting migration: Adding wb_api_key_hash column...")

        try:
            # Check if columns already exist
            inspector = db.inspect(db.engine)

            # Add column to product_groups if it doesn't exist
            product_groups_columns = [col['name'] for col in inspector.get_columns('product_groups')]
            if 'wb_api_key_hash' not in product_groups_columns:
                print("Adding wb_api_key_hash to product_groups table...")
                with db.engine.connect() as conn:
                    conn.execute(text(
                        'ALTER TABLE product_groups ADD COLUMN wb_api_key_hash VARCHAR(64);'
                    ))
                    conn.commit()
                print("[OK] Added wb_api_key_hash to product_groups")
            else:
                print("[OK] wb_api_key_hash already exists in product_groups")

            # Add column to orders if it doesn't exist
            orders_columns = [col['name'] for col in inspector.get_columns('orders')]
            if 'wb_api_key_hash' not in orders_columns:
                print("Adding wb_api_key_hash to orders table...")
                with db.engine.connect() as conn:
                    conn.execute(text(
                        'ALTER TABLE orders ADD COLUMN wb_api_key_hash VARCHAR(64);'
                    ))
                    conn.commit()
                print("[OK] Added wb_api_key_hash to orders")
            else:
                print("[OK] wb_api_key_hash already exists in orders")

            # Add indexes for better query performance
            print("Adding indexes...")
            with db.engine.connect() as conn:
                try:
                    conn.execute(text(
                        'CREATE INDEX IF NOT EXISTS idx_product_groups_wb_api_key_hash '
                        'ON product_groups(wb_api_key_hash);'
                    ))
                    conn.execute(text(
                        'CREATE INDEX IF NOT EXISTS idx_orders_wb_api_key_hash '
                        'ON orders(wb_api_key_hash);'
                    ))
                    conn.commit()
                    print("[OK] Indexes created")
                except Exception as e:
                    print(f"Note: Index creation skipped (may already exist): {e}")

            print("\n[SUCCESS] Migration completed successfully!")
            print("\nNote: Existing product groups and orders will have NULL wb_api_key_hash.")
            print("They can be edited by anyone with appropriate permissions (owner/admin/manager roles).")
            print("New groups and orders will have wb_api_key_hash set automatically.")

        except Exception as e:
            print(f"\n[ERROR] Migration failed: {e}")
            raise


if __name__ == '__main__':
    migrate()
