from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, ProductionOrder, ProductionItem, Product, CISLabel, ProductGroup, BrandExpense
from label_generator import generate_labels_sync
from session_utils import get_current_session, check_section_permission
import os
from datetime import datetime, date

production_orders_bp = Blueprint('production_orders', __name__, url_prefix='/production-orders')


@production_orders_bp.route('/', methods=['GET'])
@login_required
def get_production_orders():
    """Get all production orders for current session."""
    session, error, code = get_current_session()
    if error:
        return error, code

    try:
        production_orders = ProductionOrder.query.filter_by(session_id=session.id).order_by(
            ProductionOrder.nm_id,
            ProductionOrder.tech_size
        ).all()

        return jsonify({
            'success': True,
            'production_orders': [order.to_dict() for order in production_orders]
        })

    except Exception as e:
        current_app.logger.error(f"Error getting production orders: {e}")
        return jsonify({'error': f'Ошибка при загрузке заказов производства: {str(e)}'}), 500


@production_orders_bp.route('/move-to-production', methods=['POST'])
@login_required
def move_to_production():
    """Move selected production orders to production and generate labels."""
    session, error, code = check_section_permission('production')
    if error:
        return error, code

    try:
        data = request.get_json()
        item_ids = data.get('item_ids', [])

        if not item_ids:
            return jsonify({'error': 'Не выбраны товары для производства'}), 400

        # Get selected production orders
        production_orders = ProductionOrder.query.filter(
            ProductionOrder.id.in_(item_ids),
            ProductionOrder.session_id == session.id
        ).all()

        if not production_orders:
            return jsonify({'error': 'Товары не найдены'}), 404

        # Check that all items have "ГОТОВ" print status
        items_not_ready = [item for item in production_orders if item.print_status != 'ГОТОВ']
        if items_not_ready:
            not_ready_names = ', '.join([f"{item.title} ({item.tech_size})" for item in items_not_ready[:3]])
            if len(items_not_ready) > 3:
                not_ready_names += f" и ещё {len(items_not_ready) - 3}"
            return jsonify({
                'error': f'В производство можно передать только товары со статусом принта "ГОТОВ".\n' +
                        f'Не готовы: {not_ready_names}'
            }), 400

        # Group items by nm_id and tech_size for label generation
        items_by_product = {}
        for item in production_orders:
            key = (item.nm_id, item.tech_size)
            if key not in items_by_product:
                items_by_product[key] = []
            items_by_product[key].append(item)

        # Create labels directory
        labels_dir = os.path.join('static', 'labels')
        os.makedirs(labels_dir, exist_ok=True)

        moved_count = 0
        labels_generated = 0

        # Track brand expenses
        today = date.today()

        for (nm_id, tech_size), items in items_by_product.items():
            total_quantity = sum(item.quantity for item in items)
            labels_url = None
            labels_generated_for_group = False

            # Try to generate labels if product data is available
            product = Product.query.filter_by(nm_id=nm_id).first()
            if not product:
                current_app.logger.warning(f"Product not found for nm_id={nm_id}, skipping group")
                continue

            # Get metadata for labels
            metadata = product.get_metadata_for_labels()
            sku = product.get_sku_for_size(tech_size)

            # Find CIS label (source DataMatrix PDF) for this size
            # First, find which group this product belongs to
            product_group = ProductGroup.query.join(Product).filter(
                Product.nm_id == nm_id,
                ProductGroup.session_id == session.id
            ).first()

            if not product_group:
                current_app.logger.warning(f"Product group not found for nm_id={nm_id}, skipping group")
                continue

            # Find uploaded CIS label for this size
            cis_label = CISLabel.query.filter_by(
                group_id=product_group.id,
                tech_size=tech_size
            ).first()

            if cis_label and sku:
                # Generate labels if both CIS and SKU are available
                try:
                    # Save CIS source PDF to temp file
                    source_pdf_path = os.path.join(labels_dir, f'temp_cis_{nm_id}_{tech_size}.pdf')
                    with open(source_pdf_path, 'wb') as f:
                        f.write(cis_label.file_data)

                    # Generate labels
                    output_pdf_path, updated_source_path = generate_labels_sync(
                        source_pdf_path=source_pdf_path,
                        output_folder=labels_dir,
                        quantity=total_quantity,
                        title=metadata['title'],
                        color=metadata['color'],
                        size=tech_size,
                        material=metadata['material'],
                        country=metadata['country'],
                        ip_name=current_user.business_name or 'ИП Name',
                        article=metadata['vendor_code'],
                        ean_code=sku
                    )

                    # Update CIS label with consumed pages
                    with open(updated_source_path, 'rb') as f:
                        cis_label.file_data = f.read()
                        cis_label.file_size = len(cis_label.file_data)

                    # Clean up temp file
                    if os.path.exists(source_pdf_path):
                        os.remove(source_pdf_path)

                    # Save labels URL
                    labels_url = f'/labels/{os.path.basename(output_pdf_path)}'
                    labels_generated_for_group = True
                    labels_generated += 1

                except Exception as e:
                    current_app.logger.error(f"Error generating labels for {nm_id} {tech_size}: {e}")
                    # Continue without labels

            # Move each item to production
            for item in items:
                # Get photo from Product if available
                photo_url = item.photo_url
                if product:
                    product_photo = product.get_thumbnail() or product.get_main_image()
                    if product_photo:
                        photo_url = product_photo

                production_item = ProductionItem(
                    session_id=session.id,
                    user_id=current_user.id,
                    order_id=None,  # No direct order reference
                    order_item_id=item.order_item_id,  # For preserving order
                    nm_id=item.nm_id,
                    vendor_code=item.vendor_code,
                    brand=item.brand,
                    title=item.title,
                    photo_url=photo_url,
                    tech_size=item.tech_size,
                    color=item.color,
                    quantity=item.quantity,
                    print_link=item.print_link,
                    print_status=item.print_status,
                    priority=item.priority,
                    labels_link=labels_url if labels_generated_for_group else None
                )
                db.session.add(production_item)

                # Track brand expense
                brand_name = item.brand or 'Без бренда'
                product_name = item.title or 'Без названия'
                color_name = item.color or 'Без цвета'

                expense = BrandExpense.query.filter_by(
                    session_id=session.id,
                    date=today,
                    brand=brand_name,
                    product_name=product_name,
                    color=color_name
                ).first()

                if expense:
                    sizes = expense.get_sizes()
                    current_qty = sizes.get(item.tech_size, 0)
                    sizes[item.tech_size] = current_qty + item.quantity
                    expense.set_sizes(sizes)
                else:
                    expense = BrandExpense(
                        session_id=session.id,
                        user_id=current_user.id,
                        date=today,
                        brand=brand_name,
                        product_name=product_name,
                        color=color_name
                    )
                    sizes = {item.tech_size: item.quantity}
                    expense.set_sizes(sizes)
                    db.session.add(expense)

                # Delete from production orders
                db.session.delete(item)
                moved_count += 1

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Перемещено в производство: {moved_count} товаров\n' +
                      (f'Сгенерировано этикеток: {labels_generated}' if labels_generated > 0 else ''),
            'moved_count': moved_count,
            'labels_generated': labels_generated
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error moving to production: {e}")
        return jsonify({'error': f'Ошибка при перемещении: {str(e)}'}), 500


@production_orders_bp.route('/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_production_order(item_id):
    """Delete production order."""
    session, error, code = check_section_permission('production_orders')
    if error:
        return error, code

    try:
        production_order = ProductionOrder.query.filter_by(id=item_id, session_id=session.id).first()
        if not production_order:
            return jsonify({'error': 'Товар не найден'}), 404

        db.session.delete(production_order)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Товар удален'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting production order: {e}")
        return jsonify({'error': f'Ошибка при удалении: {str(e)}'}), 500


@production_orders_bp.route('/clear', methods=['POST'])
@login_required
def clear_production_orders():
    """Clear all production orders for current session."""
    session, error, code = check_section_permission('production_orders')
    if error:
        return error, code

    try:
        count = ProductionOrder.query.filter_by(session_id=session.id).count()

        if count == 0:
            return jsonify({'success': True, 'message': 'Нет товаров для удаления'})

        ProductionOrder.query.filter_by(session_id=session.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Удалено товаров: {count}'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing production orders: {e}")
        return jsonify({'error': f'Ошибка при очистке: {str(e)}'}), 500
