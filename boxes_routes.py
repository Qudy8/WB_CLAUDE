from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Box, BoxItem, ProductionItem, Product, Inventory, FinishedGoodsStock
from wb_api import WildberriesAPI
from session_utils import get_current_session, check_section_permission

boxes_bp = Blueprint('boxes', __name__, url_prefix='/boxes')


@boxes_bp.route('/', methods=['GET'])
@login_required
def get_boxes():
    """Get all boxes for current user."""
    session, error, code = get_current_session()
    if error:
        return error, code

    try:
        boxes = Box.query.filter_by(session_id=session.id).order_by(Box.box_number.asc()).all()

        boxes_data = []
        for box in boxes:
            box_dict = box.to_dict()
            box_dict['items'] = [item.to_dict() for item in box.items]
            boxes_data.append(box_dict)

        return jsonify({
            'success': True,
            'boxes': boxes_data
        })

    except Exception as e:
        current_app.logger.error(f"Error getting boxes: {e}")
        return jsonify({'error': f'Ошибка при загрузке коробов: {str(e)}'}), 500


@boxes_bp.route('/add-from-production', methods=['POST'])
@login_required
def add_from_production():
    """Add selected production items to boxes based on their box_number."""
    session, error, code = check_section_permission('boxes')
    if error:
        return error, code

    try:
        # Get all selected production items with box_number
        production_items = ProductionItem.query.filter_by(
            session_id=session.id,
            selected=True
        ).filter(
            ProductionItem.box_number.isnot(None),
            ProductionItem.box_number != ''
        ).all()

        if not production_items:
            return jsonify({
                'error': 'Нет выбранных товаров с номером короба. Убедитесь что:\n' +
                        '1. Товары отмечены галочкой (ВЫБРАТЬ)\n' +
                        '2. У товаров указан номер короба (КОРОБ №)'
            }), 400

        # Get API key for fetching barcodes
        api_key = current_user.get_wb_api_key(current_app.config['ENCRYPTION_KEY'])
        if not api_key:
            return jsonify({'error': 'API ключ не настроен'}), 400

        wb_api = WildberriesAPI(api_key)

        # Group items by box_number
        items_by_box = {}
        for item in production_items:
            box_num = item.box_number.strip()
            if box_num not in items_by_box:
                items_by_box[box_num] = []
            items_by_box[box_num].append(item)

        added_count = 0
        boxes_created = 0
        total_items_quantity = 0  # Track total quantity for bags

        # Process each box
        for box_number, items in items_by_box.items():
            # Find or create box
            box = Box.query.filter_by(
                session_id=session.id,
                box_number=box_number
            ).first()

            if not box:
                box = Box(
                    user_id=current_user.id,
                    session_id=session.id,
                    box_number=box_number
                )
                db.session.add(box)
                db.session.flush()
                boxes_created += 1

            # Add items to box
            for prod_item in items:
                # Get barcode from Product model
                product = Product.query.filter_by(nm_id=prod_item.nm_id).first()
                barcode = None

                if product:
                    barcode = product.get_sku_for_size(prod_item.tech_size)

                # If barcode not found in Product, try to fetch from WB API
                if not barcode:
                    try:
                        wb_product = wb_api.get_product_by_nmid(prod_item.nm_id)
                        if wb_product:
                            sizes = wb_product.get('sizes', [])
                            for size in sizes:
                                if str(size.get('techSize', '')).strip().lower() == prod_item.tech_size.strip().lower():
                                    skus = size.get('skus', [])
                                    if skus:
                                        barcode = str(skus[0])
                                        break
                    except Exception as e:
                        current_app.logger.warning(f"Error fetching barcode for nm_id={prod_item.nm_id}: {e}")

                # Check if item already exists in box
                existing_item = BoxItem.query.filter_by(
                    box_id=box.id,
                    nm_id=prod_item.nm_id,
                    tech_size=prod_item.tech_size
                ).first()

                if existing_item:
                    # Update quantity
                    existing_item.quantity += prod_item.quantity
                else:
                    # Create new box item
                    box_item = BoxItem(
                        box_id=box.id,
                        nm_id=prod_item.nm_id,
                        tech_size=prod_item.tech_size,
                        barcode=barcode or '',
                        quantity=prod_item.quantity
                    )
                    db.session.add(box_item)

                # Track total quantity for inventory deduction
                total_items_quantity += prod_item.quantity

                # Deduct from finished goods stock if available
                try:
                    # Get product from database to access card data
                    product_db = Product.query.filter_by(nm_id=prod_item.nm_id).first()

                    if product_db:
                        # Get subjectName from card data
                        card_data = product_db.get_card_data()
                        subject_name = card_data.get('subjectName', '')

                        # Get color from production item
                        product_color = prod_item.color or ''

                        if subject_name and product_color:
                            # Get first word from subjectName (e.g., "Футболки" from "Футболки")
                            first_word = subject_name.split()[0] if subject_name else ''

                            current_app.logger.info(f"Looking for finished goods: first_word='{first_word}' (from subjectName='{subject_name}'), color='{product_color}', size={prod_item.tech_size}")

                            # Find matching finished goods stock (case-insensitive, starts with first word)
                            # Query all finished goods for user and filter manually
                            all_finished_goods = FinishedGoodsStock.query.filter_by(user_id=current_user.id).all()

                            finished_good = None
                            for fg in all_finished_goods:
                                # Match if product_name starts with first word from subjectName
                                # e.g., "Футболки" matches "Футболки оверсайз", "Футболки базовые", etc.
                                if (fg.product_name and fg.color and first_word and
                                    fg.product_name.lower().startswith(first_word.lower()) and
                                    fg.color.lower() == product_color.lower()):
                                    finished_good = fg
                                    break

                            if finished_good:
                                # Get sizes stock
                                sizes_stock = finished_good.get_sizes_stock()

                                # Check if size exists and has enough quantity
                                size_key = prod_item.tech_size.upper()
                                if size_key in sizes_stock:
                                    current_qty = sizes_stock.get(size_key, 0)
                                    if current_qty >= prod_item.quantity:
                                        # Deduct quantity
                                        sizes_stock[size_key] = current_qty - prod_item.quantity
                                        finished_good.set_sizes_stock(sizes_stock)
                                        current_app.logger.info(f"✓ Deducted {prod_item.quantity} from finished goods: {subject_name} {product_color} {size_key}")
                                    else:
                                        current_app.logger.warning(f"Not enough finished goods stock for {subject_name} {product_color} {size_key}: need {prod_item.quantity}, have {current_qty}")
                                else:
                                    current_app.logger.warning(f"Size {size_key} not found in finished goods stock for {subject_name} {product_color}")
                            else:
                                current_app.logger.warning(f"Finished goods not found for: subjectName='{subject_name}', color='{product_color}'")
                except Exception as e:
                    # Don't fail the whole operation if finished goods deduction fails
                    current_app.logger.error(f"Error deducting from finished goods stock: {e}")

                # Delete production item after moving to box
                db.session.delete(prod_item)
                added_count += 1

        # Deduct inventory (bags and boxes)
        inventory = Inventory.query.filter_by(user_id=current_user.id).first()
        if not inventory:
            inventory = Inventory(user_id=current_user.id)
            db.session.add(inventory)
            db.session.flush()

        # Deduct bags (1 bag per item)
        if inventory.bags_25x30 < total_items_quantity:
            return jsonify({
                'error': f'Недостаточно пакетов в остатках. Требуется: {total_items_quantity}, доступно: {inventory.bags_25x30}'
            }), 400
        inventory.bags_25x30 -= total_items_quantity

        # Deduct boxes (1 box per created box)
        if inventory.boxes_60x40x40 < boxes_created:
            return jsonify({
                'error': f'Недостаточно коробов в остатках. Требуется: {boxes_created}, доступно: {inventory.boxes_60x40x40}'
            }), 400
        inventory.boxes_60x40x40 -= boxes_created

        db.session.commit()

        message = f'Добавлено в короба: {added_count} товар(ов)'
        if boxes_created > 0:
            message += f', создано коробов: {boxes_created}'

        return jsonify({
            'success': True,
            'message': message
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding to boxes: {e}")
        return jsonify({'error': f'Ошибка при добавлении в короба: {str(e)}'}), 500


@boxes_bp.route('/<int:box_id>/update', methods=['POST'])
@login_required
def update_box(box_id):
    """Update box fields (wb_box_id, selected, delivery_number, warehouse, delivery_date)."""
    session, error, code = check_section_permission('boxes')
    if error:
        return error, code

    try:
        box = Box.query.filter_by(id=box_id, session_id=session.id).first()
        if not box:
            return jsonify({'error': 'Короб не найден'}), 404

        data = request.get_json()

        if 'wb_box_id' in data:
            box.wb_box_id = data['wb_box_id']
        if 'selected' in data:
            box.selected = data['selected']
        if 'delivery_number' in data:
            box.delivery_number = data['delivery_number']
        if 'warehouse' in data:
            box.warehouse = data['warehouse']
        if 'delivery_date' in data:
            box.delivery_date = data['delivery_date']

        db.session.commit()

        return jsonify({'success': True, 'message': 'Короб обновлен'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при обновлении короба: {str(e)}'}), 500


@boxes_bp.route('/<int:box_id>/delete', methods=['POST'])
@login_required
def delete_box(box_id):
    """Delete box and all its items."""
    session, error, code = check_section_permission('boxes')
    if error:
        return error, code

    try:
        box = Box.query.filter_by(id=box_id, session_id=session.id).first()
        if not box:
            return jsonify({'error': 'Короб не найден'}), 404

        # Calculate total items quantity for restoring inventory
        total_items_quantity = sum(item.quantity for item in box.items)

        # Restore inventory (bags and boxes)
        inventory = Inventory.query.filter_by(user_id=current_user.id).first()
        if not inventory:
            inventory = Inventory(user_id=current_user.id)
            db.session.add(inventory)

        # Restore bags (1 bag per item)
        inventory.bags_25x30 += total_items_quantity

        # Restore boxes (1 box)
        inventory.boxes_60x40x40 += 1

        db.session.delete(box)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Короб удален, материалы возвращены в остатки'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при удалении короба: {str(e)}'}), 500


@boxes_bp.route('/clear', methods=['POST'])
@login_required
def clear_boxes():
    """Clear all boxes for current user."""
    session, error, code = check_section_permission('boxes')
    if error:
        return error, code

    try:
        boxes = Box.query.filter_by(session_id=session.id).all()

        if len(boxes) == 0:
            return jsonify({'success': True, 'message': 'Нет коробов для удаления'})

        # Calculate total items quantity for restoring inventory
        total_boxes = len(boxes)
        total_items_quantity = 0
        for box in boxes:
            total_items_quantity += sum(item.quantity for item in box.items)

        # Restore inventory (bags and boxes)
        inventory = Inventory.query.filter_by(user_id=current_user.id).first()
        if not inventory:
            inventory = Inventory(user_id=current_user.id)
            db.session.add(inventory)

        # Restore bags (1 bag per item)
        inventory.bags_25x30 += total_items_quantity

        # Restore boxes
        inventory.boxes_60x40x40 += total_boxes

        Box.query.filter_by(session_id=session.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Удалено коробов: {total_boxes}, материалы возвращены в остатки'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при очистке коробов: {str(e)}'}), 500
