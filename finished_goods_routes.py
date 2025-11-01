from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, FinishedGoodsStock

finished_goods_bp = Blueprint('finished_goods', __name__, url_prefix='/finished-goods')


@finished_goods_bp.route('/', methods=['GET'])
@login_required
def get_finished_goods():
    """Get all finished goods stock for current user."""
    try:
        stocks = FinishedGoodsStock.query.filter_by(user_id=current_user.id).order_by(FinishedGoodsStock.product_name.asc()).all()

        return jsonify({
            'success': True,
            'stocks': [stock.to_dict() for stock in stocks]
        })

    except Exception as e:
        current_app.logger.error(f"Error getting finished goods: {e}")
        return jsonify({'error': f'Ошибка при загрузке остатков: {str(e)}'}), 500


@finished_goods_bp.route('/create', methods=['POST'])
@login_required
def create_finished_good():
    """Create new finished goods stock item."""
    try:
        data = request.get_json()
        product_name = data.get('product_name', '').strip()
        color = data.get('color', '').strip()

        if not product_name:
            return jsonify({'error': 'Название товара обязательно'}), 400

        # Check if product with same name AND color already exists
        existing = FinishedGoodsStock.query.filter_by(
            user_id=current_user.id,
            product_name=product_name,
            color=color if color else None
        ).first()

        if existing:
            color_text = f' ({color})' if color else ''
            return jsonify({'error': f'Товар "{product_name}{color_text}" уже существует'}), 400

        # Create new stock item with default sizes
        stock = FinishedGoodsStock(
            user_id=current_user.id,
            product_name=product_name,
            color=color if color else None
        )

        # Initialize with default sizes (all 0)
        default_sizes = {
            'XXS': 0,
            'XS': 0,
            'S': 0,
            'M': 0,
            'L': 0,
            'XL': 0,
            'XXL': 0,
            'XXXL': 0
        }
        stock.set_sizes_stock(default_sizes)

        db.session.add(stock)
        db.session.commit()

        color_text = f' ({color})' if color else ''
        return jsonify({
            'success': True,
            'message': f'Товар "{product_name}{color_text}" добавлен',
            'stock': stock.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating finished good: {e}")
        return jsonify({'error': f'Ошибка при создании товара: {str(e)}'}), 500


@finished_goods_bp.route('/<int:stock_id>/update', methods=['POST'])
@login_required
def update_finished_good(stock_id):
    """Update finished goods stock sizes and quantities."""
    try:
        stock = FinishedGoodsStock.query.filter_by(id=stock_id, user_id=current_user.id).first()
        if not stock:
            return jsonify({'error': 'Товар не найден'}), 404

        data = request.get_json()

        # Update product name if provided
        if 'product_name' in data:
            new_name = data['product_name'].strip()
            if new_name:
                stock.product_name = new_name

        # Update color if provided
        if 'color' in data:
            stock.color = data['color'].strip() if data['color'] else None

        # Update sizes stock if provided
        if 'sizes_stock' in data:
            sizes_stock = data['sizes_stock']

            # Validate that all values are integers
            for size, qty in sizes_stock.items():
                if not isinstance(qty, int) or qty < 0:
                    return jsonify({'error': f'Некорректное количество для размера {size}'}), 400

            stock.set_sizes_stock(sizes_stock)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Товар обновлен',
            'stock': stock.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating finished good: {e}")
        return jsonify({'error': f'Ошибка при обновлении товара: {str(e)}'}), 500


@finished_goods_bp.route('/<int:stock_id>/update-size', methods=['POST'])
@login_required
def update_size_quantity(stock_id):
    """Update quantity for a specific size."""
    try:
        stock = FinishedGoodsStock.query.filter_by(id=stock_id, user_id=current_user.id).first()
        if not stock:
            return jsonify({'error': 'Товар не найден'}), 404

        data = request.get_json()
        size = data.get('size')
        quantity = data.get('quantity')

        if not size:
            return jsonify({'error': 'Размер обязателен'}), 400

        if quantity is None or not isinstance(quantity, int) or quantity < 0:
            return jsonify({'error': 'Некорректное количество'}), 400

        # Get current sizes stock
        sizes_stock = stock.get_sizes_stock()

        # Update the specific size
        sizes_stock[size] = quantity

        # Save back
        stock.set_sizes_stock(sizes_stock)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Количество для размера {size} обновлено',
            'stock': stock.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating size quantity: {e}")
        return jsonify({'error': f'Ошибка при обновлении: {str(e)}'}), 500


@finished_goods_bp.route('/<int:stock_id>/delete', methods=['POST'])
@login_required
def delete_finished_good(stock_id):
    """Delete finished goods stock item."""
    try:
        stock = FinishedGoodsStock.query.filter_by(id=stock_id, user_id=current_user.id).first()
        if not stock:
            return jsonify({'error': 'Товар не найден'}), 404

        product_name = stock.product_name
        db.session.delete(stock)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Товар "{product_name}" удален'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting finished good: {e}")
        return jsonify({'error': f'Ошибка при удалении товара: {str(e)}'}), 500


@finished_goods_bp.route('/clear', methods=['POST'])
@login_required
def clear_finished_goods():
    """Clear all finished goods stock for current user."""
    try:
        count = FinishedGoodsStock.query.filter_by(user_id=current_user.id).count()

        if count == 0:
            return jsonify({'success': True, 'message': 'Нет товаров для удаления'})

        FinishedGoodsStock.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Удалено товаров: {count}'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing finished goods: {e}")
        return jsonify({'error': f'Ошибка при очистке: {str(e)}'}), 500
