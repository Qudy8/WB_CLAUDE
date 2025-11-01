"""
Script to fix missing photos in ProductionItem by copying from Product records.
Run this once to update existing production items.
"""
from app import app, db
from models import ProductionItem, Product

def fix_production_photos():
    with app.app_context():
        # Get all production items without photos
        items_without_photo = ProductionItem.query.filter(
            (ProductionItem.photo_url == None) | (ProductionItem.photo_url == '')
        ).all()

        print(f"Found {len(items_without_photo)} production items without photos")

        updated_count = 0
        for item in items_without_photo:
            # Find corresponding product
            product = Product.query.filter_by(nm_id=item.nm_id).first()

            if product:
                photo_url = product.get_main_image()
                if photo_url:
                    item.photo_url = photo_url
                    updated_count += 1
                    print(f"Updated item {item.id} (nm_id={item.nm_id}) with photo")

        db.session.commit()
        print(f"\nSuccessfully updated {updated_count} production items with photos")

if __name__ == '__main__':
    fix_production_photos()
