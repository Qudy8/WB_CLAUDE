from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Inventory

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


@inventory_bp.route('/')
@login_required
def index():
    """Display inventory page."""
    # Get or create inventory record for current user
    inventory = Inventory.query.filter_by(user_id=current_user.id).first()

    if not inventory:
        # Create new inventory record with default values
        inventory = Inventory(user_id=current_user.id)
        db.session.add(inventory)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании записи остатков: {str(e)}', 'error')

    return render_template('inventory.html', inventory=inventory)


@inventory_bp.route('/update', methods=['POST'])
@login_required
def update():
    """Update inventory quantities."""
    try:
        inventory = Inventory.query.filter_by(user_id=current_user.id).first()

        if not inventory:
            inventory = Inventory(user_id=current_user.id)
            db.session.add(inventory)

        # Update all fields from form
        inventory.boxes_60x40x40 = int(request.form.get('boxes_60x40x40', 0))
        inventory.bags_25x30 = int(request.form.get('bags_25x30', 0))
        inventory.print_film = int(request.form.get('print_film', 0))
        inventory.paint_white = int(request.form.get('paint_white', 0))
        inventory.paint_black = int(request.form.get('paint_black', 0))
        inventory.paint_red = int(request.form.get('paint_red', 0))
        inventory.paint_yellow = int(request.form.get('paint_yellow', 0))
        inventory.paint_blue = int(request.form.get('paint_blue', 0))
        inventory.glue = int(request.form.get('glue', 0))
        inventory.label_rolls = int(request.form.get('label_rolls', 0))

        db.session.commit()
        flash('Остатки успешно обновлены!', 'success')

    except ValueError:
        db.session.rollback()
        flash('Ошибка: введите корректные числовые значения', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при обновлении остатков: {str(e)}', 'error')

    return redirect(url_for('inventory.index'))


@inventory_bp.route('/api/get', methods=['GET'])
@login_required
def api_get():
    """Get current inventory data as JSON."""
    inventory = Inventory.query.filter_by(user_id=current_user.id).first()

    if not inventory:
        return jsonify({'error': 'Данные остатков не найдены'}), 404

    return jsonify(inventory.to_dict())


@inventory_bp.route('/api/update', methods=['POST'])
@login_required
def api_update():
    """Update inventory via API."""
    try:
        data = request.get_json()

        inventory = Inventory.query.filter_by(user_id=current_user.id).first()

        if not inventory:
            inventory = Inventory(user_id=current_user.id)
            db.session.add(inventory)

        # Update fields that are provided in the request
        if 'boxes_60x40x40' in data:
            inventory.boxes_60x40x40 = int(data['boxes_60x40x40'])
        if 'bags_25x30' in data:
            inventory.bags_25x30 = int(data['bags_25x30'])
        if 'print_film' in data:
            inventory.print_film = int(data['print_film'])
        if 'paint_white' in data:
            inventory.paint_white = int(data['paint_white'])
        if 'paint_black' in data:
            inventory.paint_black = int(data['paint_black'])
        if 'paint_red' in data:
            inventory.paint_red = int(data['paint_red'])
        if 'paint_yellow' in data:
            inventory.paint_yellow = int(data['paint_yellow'])
        if 'paint_blue' in data:
            inventory.paint_blue = int(data['paint_blue'])
        if 'glue' in data:
            inventory.glue = int(data['glue'])
        if 'label_rolls' in data:
            inventory.label_rolls = int(data['label_rolls'])

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Остатки успешно обновлены',
            'data': inventory.to_dict()
        })

    except ValueError:
        db.session.rollback()
        return jsonify({'error': 'Некорректные числовые значения'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
