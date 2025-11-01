from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, FinishedGoodsStock

defects_bp = Blueprint('defects', __name__, url_prefix='/defects')


@defects_bp.route('/', methods=['GET'])
@login_required
def get_defects():
    """Get all finished goods (which include defect tracking)."""
    try:
        stocks = FinishedGoodsStock.query.filter_by(user_id=current_user.id).order_by(FinishedGoodsStock.product_name.asc()).all()

        return jsonify({
            'success': True,
            'defects': [stock.to_dict() for stock in stocks]
        })

    except Exception as e:
        current_app.logger.error(f"Error getting defects: {e}")
        return jsonify({'error': f'Ошибка при загрузке брака: {str(e)}'}), 500


@defects_bp.route('/<int:stock_id>/update-size', methods=['POST'])
@login_required
def update_defect_size(stock_id):
    """Update defect quantity for a specific size (without deducting from stock)."""
    try:
        stock = FinishedGoodsStock.query.filter_by(id=stock_id, user_id=current_user.id).first()
        if not stock:
            return jsonify({'error': 'Товар не найден'}), 404

        data = request.get_json()
        size = data.get('size')
        new_defect_qty = data.get('quantity')

        if not size:
            return jsonify({'error': 'Размер обязателен'}), 400

        if new_defect_qty is None or not isinstance(new_defect_qty, int) or new_defect_qty < 0:
            return jsonify({'error': 'Некорректное количество'}), 400

        # Get current defect quantities
        sizes_defect = stock.get_sizes_defect()

        # Update defect quantity (just save, don't deduct yet)
        sizes_defect[size] = new_defect_qty
        stock.set_sizes_defect(sizes_defect)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Количество брака для размера {size} обновлено',
            'stock': stock.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating defect size: {e}")
        return jsonify({'error': f'Ошибка при обновлении: {str(e)}'}), 500


@defects_bp.route('/apply-defects', methods=['POST'])
@login_required
def apply_defects():
    """Apply all defect quantities - deduct from stock and reset defects to zero."""
    try:
        # Get all finished goods for the user
        stocks = FinishedGoodsStock.query.filter_by(user_id=current_user.id).all()

        total_defects_applied = 0
        items_with_defects = []

        for stock in stocks:
            sizes_defect = stock.get_sizes_defect()
            sizes_stock = stock.get_sizes_stock()

            # Check if there are any defects to apply
            has_defects = any(qty > 0 for qty in sizes_defect.values())
            if not has_defects:
                continue

            items_with_defects.append(stock.product_name)

            # Apply defects for each size
            for size in ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']:
                defect_qty = sizes_defect.get(size, 0)
                if defect_qty > 0:
                    # Deduct from stock
                    current_stock = sizes_stock.get(size, 0)
                    new_stock = max(0, current_stock - defect_qty)
                    sizes_stock[size] = new_stock

                    # Reset defect to zero
                    sizes_defect[size] = 0

                    total_defects_applied += defect_qty

            # Save updated values
            stock.set_sizes_stock(sizes_stock)
            stock.set_sizes_defect(sizes_defect)

        db.session.commit()

        if total_defects_applied == 0:
            return jsonify({
                'success': True,
                'message': 'Нет брака для списания',
                'defects_applied': 0
            })

        return jsonify({
            'success': True,
            'message': f'Списано {total_defects_applied} шт. брака из остатков изделий',
            'defects_applied': total_defects_applied,
            'items_affected': items_with_defects
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error applying defects: {e}")
        return jsonify({'error': f'Ошибка при списании брака: {str(e)}'}), 500
