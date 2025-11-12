from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, PrintTask, OrderItem, Inventory, Product, ProductionOrder
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

        # Group order items by product (nm_id, vendor_code, brand, title, color)
        # and sum quantities
        from collections import defaultdict

        grouped_items = defaultdict(lambda: {'items': [], 'total_qty': 0, 'print_link': None, 'priority': None})

        for item in order_items:
            key = (item.nm_id, item.vendor_code or '', item.brand or '', item.title or '', item.color or '')
            grouped_items[key]['items'].append(item)
            grouped_items[key]['total_qty'] += item.quantity

            # Use first item's print_link and priority
            if grouped_items[key]['print_link'] is None:
                grouped_items[key]['print_link'] = item.print_link
                grouped_items[key]['priority'] = item.priority

        copied_count = 0
        deleted_count = 0
        for (nm_id, vendor_code, brand, title, color), group_data in grouped_items.items():
            items = group_data['items']
            total_qty = group_data['total_qty']
            print_link = group_data['print_link']
            priority = group_data['priority']

            # If total quantity is 0, just delete the items without copying
            if total_qty == 0:
                for item in items:
                    db.session.delete(item)
                    deleted_count += 1
                continue

            # Get data from first item
            first_item = items[0]
            order_item_ids = [item.id for item in items]

            # Get photo from Product if available, fallback to order item photo
            photo_url = first_item.photo_url
            product = Product.query.filter_by(nm_id=first_item.nm_id).first()
            if product:
                product_photo = product.get_thumbnail() or product.get_main_image()
                if product_photo:
                    photo_url = product_photo

            # Check if print task for this product already exists
            existing_task = PrintTask.query.filter_by(
                session_id=session.id,
                nm_id=first_item.nm_id,
                vendor_code=first_item.vendor_code,
                brand=first_item.brand,
                title=first_item.title,
                color=first_item.color
            ).first()

            if existing_task:
                # Update existing task - merge order_item_ids and recalculate quantity
                existing_ids = existing_task.get_order_item_ids()
                merged_ids = list(set(existing_ids + order_item_ids))  # Remove duplicates
                existing_task.set_order_item_ids(merged_ids)

                # Recalculate total quantity from all linked items
                all_items = OrderItem.query.filter(OrderItem.id.in_(merged_ids)).all()
                existing_task.quantity = sum(item.quantity for item in all_items)
                existing_task.print_link = print_link or existing_task.print_link
                existing_task.print_status = 'В РАБОТЕ'
                existing_task.priority = priority or existing_task.priority
                existing_task.photo_url = photo_url or existing_task.photo_url
            else:
                # Create new print task (grouped by product)
                print_task = PrintTask(
                    user_id=current_user.id,
                    session_id=session.id,
                    nm_id=first_item.nm_id,
                    vendor_code=first_item.vendor_code,
                    brand=first_item.brand,
                    title=first_item.title,
                    photo_url=photo_url,
                    tech_size='',  # Not used for grouped tasks
                    color=first_item.color,
                    quantity=total_qty,
                    print_link=print_link,
                    print_status='В РАБОТЕ',
                    priority=priority,
                    selected=False
                )
                print_task.set_order_item_ids(order_item_ids)
                db.session.add(print_task)
                copied_count += 1

            # Update all order items status to "В РАБОТЕ"
            for item in items:
                item.print_status = 'В РАБОТЕ'

            # Create ProductionOrder records for each size (not grouped)
            for item in items:
                # Get photo from Product if available
                item_photo_url = item.photo_url
                if product:
                    product_photo = product.get_thumbnail() or product.get_main_image()
                    if product_photo:
                        item_photo_url = product_photo

                production_order = ProductionOrder(
                    user_id=current_user.id,
                    session_id=session.id,
                    order_item_id=item.id,
                    nm_id=item.nm_id,
                    vendor_code=item.vendor_code,
                    brand=item.brand,
                    title=item.title,
                    photo_url=item_photo_url,
                    tech_size=item.tech_size,
                    color=item.color,
                    quantity=item.quantity,
                    print_link=item.print_link,
                    print_status='В РАБОТЕ',
                    priority=item.priority,
                    selected=False
                )
                db.session.add(production_order)

        db.session.commit()

        # Build success message
        message_parts = []
        if copied_count > 0:
            message_parts.append(f'Скопировано заданий на печать: {copied_count}')
        if deleted_count > 0:
            message_parts.append(f'Удалено товаров с количеством 0: {deleted_count}')

        message = '\n'.join(message_parts) if message_parts else 'Нет изменений'

        return jsonify({
            'success': True,
            'message': message,
            'copied_count': copied_count,
            'deleted_count': deleted_count
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

        # Sync print_status back to all linked OrderItems if it was updated
        if 'print_status' in data:
            order_item_ids = print_task.get_order_item_ids()
            if order_item_ids:
                order_items = OrderItem.query.filter(OrderItem.id.in_(order_item_ids)).all()
                for order_item in order_items:
                    order_item.print_status = data['print_status']

                # Also sync to ProductionOrders
                production_orders = ProductionOrder.query.filter(ProductionOrder.order_item_id.in_(order_item_ids)).all()
                for prod_order in production_orders:
                    prod_order.print_status = data['print_status']

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
            inventory = Inventory.query.filter_by(session_id=session.id).first()
            if not inventory:
                inventory = Inventory(user_id=current_user.id, session_id=session.id)
                db.session.add(inventory)
                db.session.flush()

            # Check if enough film is available
            if inventory.print_film < print_task.film_usage:
                return jsonify({
                    'error': f'Недостаточно пленки в остатках. Требуется: {print_task.film_usage} м, доступно: {inventory.print_film} м'
                }), 400

            # Deduct film usage
            inventory.print_film -= print_task.film_usage

        # Update all linked order items status to "ГОТОВ" and then delete them
        order_item_ids = print_task.get_order_item_ids()
        if order_item_ids:
            order_items = OrderItem.query.filter(OrderItem.id.in_(order_item_ids)).all()

            # First, sync status to ProductionOrders (before deleting OrderItems)
            production_orders = ProductionOrder.query.filter(ProductionOrder.order_item_id.in_(order_item_ids)).all()
            for prod_order in production_orders:
                prod_order.print_status = 'ГОТОВ'

            # Now delete order items from Orders tab (task completed, no longer needed there)
            for order_item in order_items:
                db.session.delete(order_item)

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
