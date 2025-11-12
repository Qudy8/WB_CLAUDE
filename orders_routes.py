from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Order, OrderItem
from wb_api import WildberriesAPI
from session_utils import get_current_session, check_section_permission, check_wb_cabinet_permission

orders_bp = Blueprint('orders', __name__, url_prefix='/orders')


@orders_bp.route('/', methods=['GET'])
@login_required
def get_orders():
    """Get all orders for current user."""
    session, error, code = get_current_session()
    if error:
        return error, code

    orders = Order.query.filter_by(session_id=session.id).order_by(Order.created_at.desc()).all()
    return jsonify({
        'success': True,
        'orders': [order.to_dict() for order in orders]
    })


@orders_bp.route('/<int:order_id>', methods=['GET'])
@login_required
def get_order(order_id):
    """Get specific order with items."""
    session, error, code = get_current_session()
    if error:
        return error, code

    order = Order.query.filter_by(id=order_id, session_id=session.id).first()
    if not order:
        return jsonify({'success': False, 'error': 'Заказ не найден'}), 404

    order_data = order.to_dict()
    order_data['items'] = [item.to_dict() for item in order.items]

    return jsonify({
        'success': True,
        'order': order_data
    })


@orders_bp.route('/create', methods=['POST'])
@login_required
def create_order():
    """Create new order with products from WB API."""
    session, error, code = check_section_permission('orders')
    if error:
        return error, code

    try:
        data = request.get_json()
        order_name = data.get('name', '').strip()
        nm_ids = data.get('nm_ids', [])

        if not order_name:
            return jsonify({'success': False, 'error': 'Введите название заказа'}), 400

        if not nm_ids or len(nm_ids) == 0:
            return jsonify({'success': False, 'error': 'Добавьте хотя бы один товар'}), 400

        # Convert to integers
        try:
            nm_ids = [int(nm_id) for nm_id in nm_ids]
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Неверный формат артикулов'}), 400

        # Get API key
        api_key = current_user.get_wb_api_key(current_app.config['ENCRYPTION_KEY'])
        if not api_key:
            return jsonify({'success': False, 'error': 'API ключ не настроен'}), 400

        # Fetch products from WB API
        wb_api = WildberriesAPI(api_key)
        wb_products_dict = wb_api.get_products_by_nmids(nm_ids)

        if not wb_products_dict:
            return jsonify({'success': False, 'error': 'Товары не найдены'}), 404

        # Get API key hash for cabinet identification
        api_key_hash = current_user.get_wb_api_key_hash(current_app.config['ENCRYPTION_KEY'])

        # Create order
        order = Order(
            user_id=current_user.id,
            session_id=session.id,
            name=order_name,
            wb_api_key_hash=api_key_hash
        )
        db.session.add(order)
        db.session.flush()  # Get order ID

        # Create order items for each product size
        for nm_id, card in wb_products_dict.items():
            if card is None:
                continue  # Skip if product not found

            # Ensure all values are strings, not lists
            vendor_code = str(card.get('vendorCode', '') or '')
            brand = str(card.get('brand', '') or '')
            title = str(card.get('title', '') or '')

            # Get first photo
            photos = card.get('photos', [])
            photo_url = ''
            if photos and len(photos) > 0:
                photo_url = str(photos[0].get('c246x328', photos[0].get('tm', '')) or '')

            # Get sizes
            sizes = card.get('sizes', [])

            # Try to extract color from characteristics (do once for all sizes)
            color = ''
            characteristics = card.get('characteristics', [])
            if characteristics:
                for char in characteristics:
                    if isinstance(char, dict) and char.get('name') == 'Цвет':
                        color_value = char.get('value', '')
                        # Make sure it's a string, not a list
                        if isinstance(color_value, list):
                            color = ', '.join(str(v) for v in color_value if v)
                        else:
                            color = str(color_value) if color_value else ''
                        break

            if not sizes:
                # If no sizes, create one item without size
                order_item = OrderItem(
                    order_id=order.id,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    brand=brand,
                    title=title,
                    photo_url=photo_url,
                    tech_size='',
                    color=color,
                    quantity=0
                )
                db.session.add(order_item)
            else:
                # Create item for EACH size (photo only for first size)
                for idx, size in enumerate(sizes):
                    tech_size = str(size.get('techSize', '') or '')

                    # Photo only for the first size
                    item_photo_url = photo_url if idx == 0 else ''

                    order_item = OrderItem(
                        order_id=order.id,
                        nm_id=nm_id,
                        vendor_code=vendor_code,
                        brand=brand,
                        title=title,
                        photo_url=item_photo_url,
                        tech_size=tech_size,
                        color=color,
                        quantity=0
                    )
                    db.session.add(order_item)

        db.session.commit()

        return jsonify({
            'success': True,
            'order_id': order.id,
            'message': 'Заказ успешно создан'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orders_bp.route('/<int:order_id>/items/<int:item_id>/update', methods=['POST'])
@login_required
def update_order_item(order_id, item_id):
    """Update order item fields."""
    session, error, code = check_section_permission('orders')
    if error:
        return error, code

    try:
        # Verify order belongs to user
        order = Order.query.filter_by(id=order_id, session_id=session.id).first()
        if not order:
            return jsonify({'success': False, 'error': 'Заказ не найден'}), 404

        # Check if user has permission to edit this order (based on WB cabinet)
        allowed, error, code = check_wb_cabinet_permission(order)
        if not allowed:
            return error, code

        # Get order item
        item = OrderItem.query.filter_by(id=item_id, order_id=order_id).first()
        if not item:
            return jsonify({'success': False, 'error': 'Товар не найден'}), 404

        # Update fields
        data = request.get_json()

        if 'quantity' in data:
            try:
                item.quantity = int(data['quantity'])
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Неверное количество'}), 400

        if 'print_link' in data:
            item.print_link = data['print_link'].strip()

        if 'print_status' in data:
            item.print_status = data['print_status'].strip()

        if 'priority' in data:
            item.priority = data['priority'].strip()

        if 'selected' in data:
            item.selected = bool(data['selected'])

        db.session.commit()

        return jsonify({
            'success': True,
            'item': item.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orders_bp.route('/<int:order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    """Delete order."""
    session, error, code = check_section_permission('orders')
    if error:
        return error, code

    try:
        order = Order.query.filter_by(id=order_id, session_id=session.id).first()
        if not order:
            return jsonify({'success': False, 'error': 'Заказ не найден'}), 404

        # Check if user has permission to delete this order (based on WB cabinet)
        allowed, error, code = check_wb_cabinet_permission(order)
        if not allowed:
            return error, code

        db.session.delete(order)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Заказ удален'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
