"""
Migration script to add order_item_ids_json field to print_tasks table
"""
from app import app, db
from sqlalchemy import text

def migrate():
    """Add order_item_ids_json field to print_tasks table"""
    with app.app_context():
        try:
            # Check if column exists
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('print_tasks')]

            if 'order_item_ids_json' in columns:
                print("Column order_item_ids_json already exists in print_tasks table")
            else:
                # Add the new column
                print("Adding order_item_ids_json column to print_tasks table...")

                # SQLite and PostgreSQL compatible ALTER TABLE
                with db.engine.connect() as conn:
                    conn.execute(text("""
                        ALTER TABLE print_tasks
                        ADD COLUMN order_item_ids_json TEXT
                    """))
                    conn.commit()

                print("Successfully added order_item_ids_json column")

        except Exception as e:
            print(f"Error during migration: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    migrate()
