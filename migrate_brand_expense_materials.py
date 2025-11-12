"""
Migration script to add material tracking columns to BrandExpense table
Adds: boxes_used, bags_used, film_used
"""
from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        try:
            # Check if table exists first
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()

            if 'brand_expense' not in tables:
                print("INFO: brand_expense table does not exist yet, skipping migration")
                return

            # Check if columns already exist
            existing_columns = [col['name'] for col in inspector.get_columns('brand_expense')]

            columns_to_add = []
            if 'boxes_used' not in existing_columns:
                columns_to_add.append('boxes_used')
            if 'bags_used' not in existing_columns:
                columns_to_add.append('bags_used')
            if 'film_used' not in existing_columns:
                columns_to_add.append('film_used')

            if not columns_to_add:
                print("OK: All material tracking columns already exist in brand_expense table")
                return

            print(f"Adding columns to brand_expense table: {', '.join(columns_to_add)}")

            # Add new columns
            with db.engine.connect() as conn:
                if 'boxes_used' in columns_to_add:
                    conn.execute(text('ALTER TABLE brand_expense ADD COLUMN boxes_used FLOAT DEFAULT 0'))
                    print("OK: Added boxes_used column")

                if 'bags_used' in columns_to_add:
                    conn.execute(text('ALTER TABLE brand_expense ADD COLUMN bags_used FLOAT DEFAULT 0'))
                    print("OK: Added bags_used column")

                if 'film_used' in columns_to_add:
                    conn.execute(text('ALTER TABLE brand_expense ADD COLUMN film_used FLOAT DEFAULT 0'))
                    print("OK: Added film_used column")

                conn.commit()

            print("\nOK: Migration completed successfully!")
            print("Material tracking columns added to BrandExpense table:")
            print("  - boxes_used (boxes usage)")
            print("  - bags_used (bags usage)")
            print("  - film_used (film usage in meters)")

        except Exception as e:
            print(f"\nERROR: Migration failed: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == '__main__':
    migrate()
