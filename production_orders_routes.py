from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, ProductionOrder, ProductionItem, Product, CISLabel, ProductGroup, BrandExpense, Inventory
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

        # STEP 1: Validate ALL items before moving anything
        validation_errors = []

        for (nm_id, tech_size), items in items_by_product.items():
            first_item = items[0]
            item_desc = f"{first_item.title or 'товар'} (артикул WB: {nm_id}, размер: {tech_size})"

            # Check if product exists
            product = Product.query.filter_by(nm_id=nm_id).first()
            if not product:
                validation_errors.append(f"❌ {item_desc}: Товар не найден в базе данных")
                continue

            # Check if product group exists
            product_group = ProductGroup.query.join(Product).filter(
                Product.nm_id == nm_id,
                ProductGroup.session_id == session.id
            ).first()

            if not product_group:
                validation_errors.append(f"❌ {item_desc}: Группа товаров не найдена")
                continue

            # Check if SKU exists for this size
            sku = product.get_sku_for_size(tech_size)
            if not sku:
                validation_errors.append(f"❌ {item_desc}: Не найден штрих-код (SKU) для размера {tech_size}")
                continue

            # Check if CIS label exists for this size
            cis_label = CISLabel.query.filter_by(
                group_id=product_group.id,
                tech_size=tech_size
            ).first()

            if not cis_label:
                validation_errors.append(f"❌ {item_desc}: Не загружена CIS этикетка для размера {tech_size}")
                continue

            # Check if CIS label has enough pages
            from pypdf import PdfReader
            import io
            try:
                pdf_reader = PdfReader(io.BytesIO(cis_label.file_data))
                available_pages = len(pdf_reader.pages)
                total_quantity = sum(item.quantity for item in items)

                if available_pages < total_quantity:
                    validation_errors.append(
                        f"❌ {item_desc}: Недостаточно страниц в CIS этикетке. "
                        f"Требуется: {total_quantity}, доступно: {available_pages}"
                    )
                    continue
            except Exception as e:
                validation_errors.append(f"❌ {item_desc}: Ошибка чтения CIS этикетки - {str(e)}")
                continue

        # If there are any validation errors, return them and don't move anything
        if validation_errors:
            error_message = "⚠️ Невозможно переместить товары в производство:\n\n" + "\n".join(validation_errors)
            error_message += "\n\n💡 Устраните указанные проблемы и попробуйте снова."
            return jsonify({'error': error_message}), 400

        # STEP 2: All validations passed - now generate labels and move items
        # Create labels directory
        labels_dir = os.path.join('static', 'labels')
        os.makedirs(labels_dir, exist_ok=True)

        moved_count = 0
        labels_generated = 0
        total_items_quantity = 0  # Track total quantity for bags inventory

        # Track brand expenses
        today = date.today()

        for (nm_id, tech_size), items in items_by_product.items():
            total_quantity = sum(item.quantity for item in items)
            labels_url = None
            labels_generated_for_group = False

            # Get product data (we already validated it exists)
            product = Product.query.filter_by(nm_id=nm_id).first()
            metadata = product.get_metadata_for_labels()
            sku = product.get_sku_for_size(tech_size)

            # Get product group (we already validated it exists)
            product_group = ProductGroup.query.join(Product).filter(
                Product.nm_id == nm_id,
                ProductGroup.session_id == session.id
            ).first()

            # Get CIS label (we already validated it exists)
            cis_label = CISLabel.query.filter_by(
                group_id=product_group.id,
                tech_size=tech_size
            ).first()

            # Generate labels (this should never fail because we validated everything)
            try:
                # Save CIS source PDF to temp file
                temp_dir = os.path.join('temp')
                os.makedirs(temp_dir, exist_ok=True)

                source_pdf_path = os.path.join(temp_dir, f'source_{nm_id}_{tech_size}.pdf')
                with open(source_pdf_path, 'wb') as f:
                    f.write(cis_label.file_data)

                # Generate labels
                ip_name = getattr(current_user, 'ip_name', '') or ''
                label_settings = current_user.get_label_settings()

                output_pdf_path, updated_source_path = generate_labels_sync(
                    local_pdf_path=source_pdf_path,
                    quantity=total_quantity,
                    title=metadata['title'],
                    color=metadata['color'],
                    wb_size=tech_size,
                    material=metadata['material'],
                    ean_code=sku or '',
                    country=metadata['country'],
                    ip_name=ip_name,
                    nm_id=nm_id,
                    label_settings=label_settings
                )

                # Save generated labels
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                final_filename = f'labels_po_{nm_id}_{tech_size}_{timestamp}.pdf'
                final_path = os.path.join(labels_dir, final_filename)

                # Copy generated labels to static/labels
                import shutil
                shutil.copy(output_pdf_path, final_path)

                # Update CIS label with consumed pages
                with open(updated_source_path, 'rb') as f:
                    cis_label.file_data = f.read()
                    cis_label.file_size = len(cis_label.file_data)

                # Clean up temp files
                for temp_file in [source_pdf_path, output_pdf_path, updated_source_path]:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except Exception as cleanup_error:
                            current_app.logger.warning(f"Failed to cleanup temp file {temp_file}: {cleanup_error}")

                # Save labels URL
                labels_url = f'/labels/{final_filename}'
                labels_generated_for_group = True
                labels_generated += 1

            except Exception as e:
                # If label generation fails after validation, rollback everything
                db.session.rollback()
                current_app.logger.error(f"Error generating labels for {nm_id} {tech_size}: {e}")

                first_item = items[0]
                item_desc = f"{first_item.title or 'товар'} (артикул WB: {nm_id}, размер: {tech_size})"

                error_message = f"⚠️ Ошибка генерации этикеток для:\n\n❌ {item_desc}\n\nДетали ошибки: {str(e)}\n\n"
                error_message += "💡 Товары НЕ были перемещены в производство. Обратитесь к администратору."

                return jsonify({'error': error_message}), 500

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

                # Track total quantity for bags inventory deduction
                total_items_quantity += item.quantity

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
                    # Add bags used (1 bag per item)
                    expense.bags_used = (expense.bags_used or 0) + item.quantity
                else:
                    expense = BrandExpense(
                        session_id=session.id,
                        user_id=current_user.id,
                        date=today,
                        brand=brand_name,
                        product_name=product_name,
                        color=color_name,
                        bags_used=item.quantity  # 1 bag per item
                    )
                    sizes = {item.tech_size: item.quantity}
                    expense.set_sizes(sizes)
                    db.session.add(expense)

                # Delete from production orders
                db.session.delete(item)
                moved_count += 1

        # Deduct bags from inventory (1 bag per item)
        if total_items_quantity > 0:
            inventory = Inventory.query.filter_by(session_id=session.id).first()
            if not inventory:
                inventory = Inventory(user_id=current_user.id, session_id=session.id)
                db.session.add(inventory)
                db.session.flush()

            # Check if enough bags available
            if inventory.bags_25x30 < total_items_quantity:
                db.session.rollback()
                return jsonify({
                    'error': f'Недостаточно пакетов в остатках для производства.\n' +
                            f'Требуется: {total_items_quantity}, доступно: {inventory.bags_25x30}'
                }), 400

            # Deduct bags
            inventory.bags_25x30 -= total_items_quantity
            current_app.logger.info(f"Deducted {total_items_quantity} bags from inventory")

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
