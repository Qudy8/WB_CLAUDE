from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, PrintTask, OrderItem, Inventory
from session_utils import get_current_session, check_section_permission

print_tasks_bp = Blueprint('print_tasks', __name__, url_prefix='/print-tasks')


@print_tasks_bp.route('/', methods=['GET'])
@login_required
def get_print_tasks():
    """Get all print tasks for current session."""
    session, error, code = get_current_session()
    if error:
        return error, code

    try:
        print_tasks = PrintTask.query.filter_by(session_id=session.id).order_by(PrintTask.created_at.desc()).all()

        return jsonify({
            'success': True,
            'print_tasks': [task.to_dict() for task in print_tasks]
        })

    except Exception as e:
        current_app.logger.error(f"Error getting print tasks: {e}")
        return jsonify({'error': f'Ошибка при загрузке заданий на печать: {str(e)}'}), 500


@print_tasks_bp.route('/copy-from-order', methods=['POST'])
@login_required
def copy_from_order():
    """Copy selected order items to print tasks."""
    session, error, code = check_section_permission('print_tasks')
    if error:
        return error, code

    try:
        data = request.get_json()
        order_id = data.get('order_id')
        item_ids = data.get('item_ids', [])

        if not item_ids:
            return jsonify({'error': 'Не выбраны товары для копирования'}), 400

        # Get selected order items
        order_items = OrderItem.query.filter(
            OrderItem.id.in_(item_ids),
            OrderItem.order_id == order_id
        ).all()

        if not order_items:
            return jsonify({'error': 'Товары не найдены'}), 404

        # Check if user owns the order
        first_item = order_items[0]
        if first_item.order.user_id != current_user.id:
            return jsonify({'error': 'Доступ запрещен'}), 403

        # Check that items don't already have "ГОТОВ" status
        items_already_ready = [item for item in order_items if item.print_status == 'ГОТОВ']
        if items_already_ready:
            ready_names = ', '.join([f"{item.title} ({item.tech_size})" for item in items_already_ready[:3]])
            if len(items_already_ready) > 3:
                ready_names += f" и ещё {len(items_already_ready) - 3}"
            return jsonify({
                'error': f'Нельзя копировать товары со статусом "ГОТОВ".\n' +
                        f'Уже готовы: {ready_names}'
            }), 400

        copied_count = 0
        for item in order_items:
            # Check if this order item already has a print task
            existing_task = PrintTask.query.filter_by(
                session_id=session.id,
                order_item_id=item.id
            ).first()

            if existing_task:
                # Update existing task
                existing_task.quantity = item.quantity
                existing_task.print_link = item.print_link
                existing_task.print_status = 'В РАБОТЕ'
                existing_task.priority = item.priority
                existing_task.photo_url = item.photo_url
                existing_task.color = item.color
            else:
                # Create new print task
                print_task = PrintTask(
                    user_id=current_user.id,
                    session_id=session.id,
                    order_item_id=item.id,
                    nm_id=item.nm_id,
                    vendor_code=item.vendor_code,
                    brand=item.brand,
                    title=item.title,
                    photo_url=item.photo_url,
                    tech_size=item.tech_size,
                    color=item.color,
                    quantity=item.quantity,
                    print_link=item.print_link,
                    print_status='В РАБОТЕ',
                    priority=item.priority,
                    selected=False
                )
                db.session.add(print_task)
                copied_count += 1

            # Update order item status to "В РАБОТЕ"
            item.print_status = 'В РАБОТЕ'

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Скопировано заданий на печать: {copied_count}',
            'copied_count': copied_count
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error copying to print tasks: {e}")
        return jsonify({'error': f'Ошибка при копировании: {str(e)}'}), 500


@print_tasks_bp.route('/<int:task_id>/update', methods=['POST'])
@login_required
def update_print_task(task_id):
    """Update print task field and sync status with OrderItem."""
    session, error, code = check_section_permission('print_tasks')
    if error:
        return error, code

    try:
        print_task = PrintTask.query.filter_by(id=task_id, session_id=session.id).first()
        if not print_task:
            return jsonify({'error': 'Задание не найдено'}), 404

        data = request.get_json()

        # Update print task fields
        for field in ['quantity', 'film_usage', 'print_link', 'print_status', 'priority', 'selected']:
            if field in data:
                setattr(print_task, field, data[field])

        # Sync print_status back to OrderItem if it was updated
        if 'print_status' in data and print_task.order_item_id:
            order_item = OrderItem.query.get(print_task.order_item_id)
            if order_item:
                order_item.print_status = data['print_status']

        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating print task: {e}")
        return jsonify({'error': f'Ошибка при обновлении: {str(e)}'}), 500


@print_tasks_bp.route('/<int:task_id>/complete', methods=['POST'])
@login_required
def complete_print_task(task_id):
    """Mark print task as complete and update order item status."""
    session, error, code = check_section_permission('print_tasks')
    if error:
        return error, code

    try:
        print_task = PrintTask.query.filter_by(id=task_id, session_id=session.id).first()
        if not print_task:
            return jsonify({'error': 'Задание не найдено'}), 404

        # Deduct film usage from inventory if specified
        if print_task.film_usage and print_task.film_usage > 0:
            inventory = Inventory.query.filter_by(user_id=current_user.id).first()
            if not inventory:
                inventory = Inventory(user_id=current_user.id)
                db.session.add(inventory)
                db.session.flush()

            # Check if enough film is available
            if inventory.print_film < print_task.film_usage:
                return jsonify({
                    'error': f'Недостаточно пленки в остатках. Требуется: {print_task.film_usage} м, доступно: {inventory.print_film} м'
                }), 400

            # Deduct film usage
            inventory.print_film -= print_task.film_usage

        # Update order item status to "ГОТОВ" if it exists
        if print_task.order_item_id:
            order_item = OrderItem.query.get(print_task.order_item_id)
            if order_item:
                order_item.print_status = 'ГОТОВ'

        # Delete print task
        db.session.delete(print_task)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Задание завершено'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error completing print task: {e}")
        return jsonify({'error': f'Ошибка при завершении: {str(e)}'}), 500


@print_tasks_bp.route('/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_print_task(task_id):
    """Delete print task."""
    session, error, code = check_section_permission('print_tasks')
    if error:
        return error, code

    try:
        print_task = PrintTask.query.filter_by(id=task_id, session_id=session.id).first()
        if not print_task:
            return jsonify({'error': 'Задание не найдено'}), 404

        db.session.delete(print_task)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Задание удалено'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting print task: {e}")
        return jsonify({'error': f'Ошибка при удалении: {str(e)}'}), 500


@print_tasks_bp.route('/clear', methods=['POST'])
@login_required
def clear_print_tasks():
    """Clear all print tasks for current session."""
    session, error, code = check_section_permission('print_tasks')
    if error:
        return error, code

    try:
        count = PrintTask.query.filter_by(session_id=session.id).count()

        if count == 0:
            return jsonify({'success': True, 'message': 'Нет заданий для удаления'})

        PrintTask.query.filter_by(session_id=session.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Удалено заданий: {count}'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing print tasks: {e}")
        return jsonify({'error': f'Ошибка при очистке: {str(e)}'}), 500
