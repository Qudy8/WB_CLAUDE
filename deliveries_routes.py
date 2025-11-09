from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Delivery, DeliveryBox, Box
from barcode_generator import generate_delivery_barcodes
from session_utils import get_current_session, check_section_permission
import os
import shutil

deliveries_bp = Blueprint('deliveries', __name__, url_prefix='/deliveries')


@deliveries_bp.route('/', methods=['GET'])
@login_required
def get_deliveries():
    """Get all deliveries for current user."""
    session, error, code = get_current_session()
    if error:
        return error, code

    try:
        deliveries = Delivery.query.filter_by(session_id=session.id).order_by(Delivery.created_at.desc()).all()

        deliveries_data = []
        for delivery in deliveries:
            delivery_dict = delivery.to_dict()
            delivery_dict['boxes'] = [box.to_dict() for box in delivery.boxes]
            deliveries_data.append(delivery_dict)

        return jsonify({
            'success': True,
            'deliveries': deliveries_data
        })

    except Exception as e:
        current_app.logger.error(f"Error getting deliveries: {e}")
        return jsonify({'error': f'Ошибка при загрузке поставок: {str(e)}'}), 500


@deliveries_bp.route('/add-from-boxes', methods=['POST'])
@login_required
def add_from_boxes():
    """Add selected boxes to a new delivery."""
    session, error, code = check_section_permission('deliveries')
    if error:
        return error, code

    try:
        # Get all selected boxes
        boxes = Box.query.filter_by(
            session_id=session.id,
            selected=True
        ).all()

        if not boxes:
            return jsonify({
                'error': 'Нет выбранных коробов. Отметьте короба галочкой в разделе "Короба"'
            }), 400

        # Check that all boxes have required delivery info
        missing_info = []
        for box in boxes:
            if not box.delivery_date:
                missing_info.append(f'Короб №{box.box_number}: не указана дата поставки')
            if not box.delivery_number:
                missing_info.append(f'Короб №{box.box_number}: не указан номер поставки')
            if not box.warehouse:
                missing_info.append(f'Короб №{box.box_number}: не указан склад назначения')

        if missing_info:
            return jsonify({
                'error': 'Заполните обязательные поля для всех выбранных коробов:\n' + '\n'.join(missing_info)
            }), 400

        # Group boxes by delivery info (delivery_date, delivery_number, warehouse)
        deliveries_map = {}
        for box in boxes:
            key = (box.delivery_date, box.delivery_number, box.warehouse)
            if key not in deliveries_map:
                deliveries_map[key] = []
            deliveries_map[key].append(box)

        created_deliveries = []

        # Create delivery for each unique combination
        for (delivery_date, delivery_number, warehouse), box_group in deliveries_map.items():
            # Create delivery
            delivery = Delivery(
                user_id=current_user.id,
                session_id=session.id,
                delivery_date=delivery_date,
                delivery_number=delivery_number,
                warehouse=warehouse,
                status='ГОТОВ'
            )
            db.session.add(delivery)
            db.session.flush()  # Get delivery ID

            # Add boxes to delivery
            for box in box_group:
                # Create snapshot of box items
                items_data = []
                for item in box.items:
                    items_data.append({
                        'nm_id': item.nm_id,
                        'tech_size': item.tech_size,
                        'barcode': item.barcode,
                        'quantity': item.quantity
                    })

                delivery_box = DeliveryBox(
                    delivery_id=delivery.id,
                    box_number=box.box_number,
                    wb_box_id=box.wb_box_id
                )
                delivery_box.set_items(items_data)
                db.session.add(delivery_box)

                # Delete original box
                db.session.delete(box)

            created_deliveries.append(delivery)

        db.session.commit()

        # Generate barcodes for each created delivery
        for delivery_obj in created_deliveries:
            try:
                # Prepare boxes with items data
                boxes_with_items = []
                for dbox in delivery_obj.boxes:
                    items = dbox.get_items()
                    boxes_with_items.append((dbox, items))

                # Generate barcode PDFs
                box_pdf_path, delivery_pdf_path = generate_delivery_barcodes(delivery_obj, boxes_with_items)

                # Create static/barcodes directory if not exists
                barcodes_dir = os.path.join('static', 'barcodes')
                os.makedirs(barcodes_dir, exist_ok=True)

                # Generate filenames
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                box_filename = f'boxes_{delivery_obj.id}_{timestamp}.pdf'
                delivery_filename = f'delivery_{delivery_obj.id}_{timestamp}.pdf'

                # Copy to static/barcodes
                final_box_path = os.path.join(barcodes_dir, box_filename)
                final_delivery_path = os.path.join(barcodes_dir, delivery_filename)

                shutil.copy(box_pdf_path, final_box_path)
                shutil.copy(delivery_pdf_path, final_delivery_path)

                # Clean up temp files
                os.remove(box_pdf_path)
                os.remove(delivery_pdf_path)

                # Update delivery record with PDF paths
                delivery_obj.box_barcode_pdf = f'/barcodes/{box_filename}'
                delivery_obj.delivery_barcode_pdf = f'/barcodes/{delivery_filename}'

            except Exception as e:
                current_app.logger.error(f"Error generating barcodes for delivery {delivery_obj.id}: {e}")
                # Continue with other deliveries even if one fails

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Создано поставок: {len(created_deliveries)}. Штрих-коды сгенерированы.',
            'deliveries': [d.delivery_number for d in created_deliveries]
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding to deliveries: {e}")
        return jsonify({'error': f'Ошибка при создании поставок: {str(e)}'}), 500


@deliveries_bp.route('/<int:delivery_id>/update-status', methods=['POST'])
@login_required
def update_status(delivery_id):
    """Update delivery status."""
    session, error, code = check_section_permission('deliveries')
    if error:
        return error, code

    try:
        delivery = Delivery.query.filter_by(id=delivery_id, session_id=session.id).first()
        if not delivery:
            return jsonify({'error': 'Поставка не найдена'}), 404

        data = request.get_json()
        status = data.get('status')

        if status not in ['ГОТОВ', 'В АРХИВЕ']:
            return jsonify({'error': 'Недопустимый статус'}), 400

        delivery.status = status
        db.session.commit()

        return jsonify({'success': True, 'message': 'Статус обновлен'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при обновлении статуса: {str(e)}'}), 500


@deliveries_bp.route('/<int:delivery_id>/delete', methods=['POST'])
@login_required
def delete_delivery(delivery_id):
    """Delete delivery."""
    session, error, code = check_section_permission('deliveries')
    if error:
        return error, code

    try:
        delivery = Delivery.query.filter_by(id=delivery_id, session_id=session.id).first()
        if not delivery:
            return jsonify({'error': 'Поставка не найдена'}), 404

        db.session.delete(delivery)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Поставка удалена'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при удалении поставки: {str(e)}'}), 500


@deliveries_bp.route('/<int:delivery_id>/generate-barcodes', methods=['POST'])
@login_required
def generate_barcodes(delivery_id):
    """Generate barcode PDFs for delivery and boxes."""
    session, error, code = check_section_permission('deliveries')
    if error:
        return error, code

    try:
        delivery = Delivery.query.filter_by(id=delivery_id, session_id=session.id).first()
        if not delivery:
            return jsonify({'error': 'Поставка не найдена'}), 404

        # Check that delivery has boxes
        if not delivery.boxes:
            return jsonify({'error': 'В поставке нет коробов'}), 400

        # Prepare boxes with items data
        boxes_with_items = []
        for dbox in delivery.boxes:
            items = dbox.get_items()  # Get items from JSON
            boxes_with_items.append((dbox, items))

        # Generate barcode PDFs
        box_pdf_path, delivery_pdf_path = generate_delivery_barcodes(delivery, boxes_with_items)

        # Create static/barcodes directory if not exists
        barcodes_dir = os.path.join('static', 'barcodes')
        os.makedirs(barcodes_dir, exist_ok=True)

        # Generate filenames
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        box_filename = f'boxes_{delivery_id}_{timestamp}.pdf'
        delivery_filename = f'delivery_{delivery_id}_{timestamp}.pdf'

        # Copy to static/barcodes
        final_box_path = os.path.join(barcodes_dir, box_filename)
        final_delivery_path = os.path.join(barcodes_dir, delivery_filename)

        shutil.copy(box_pdf_path, final_box_path)
        shutil.copy(delivery_pdf_path, final_delivery_path)

        # Clean up temp files
        os.remove(box_pdf_path)
        os.remove(delivery_pdf_path)

        # Update delivery record with PDF paths
        delivery.box_barcode_pdf = f'/barcodes/{box_filename}'
        delivery.delivery_barcode_pdf = f'/barcodes/{delivery_filename}'
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Штрих-коды успешно сгенерированы',
            'box_barcode_pdf': delivery.box_barcode_pdf,
            'delivery_barcode_pdf': delivery.delivery_barcode_pdf
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating barcodes: {e}")
        return jsonify({'error': f'Ошибка при генерации штрих-кодов: {str(e)}'}), 500


@deliveries_bp.route('/clear', methods=['POST'])
@login_required
def clear_deliveries():
    """Clear all deliveries for current user."""
    session, error, code = check_section_permission('deliveries')
    if error:
        return error, code

    try:
        count = Delivery.query.filter_by(session_id=session.id).count()

        if count == 0:
            return jsonify({'success': True, 'message': 'Нет поставок для удаления'})

        Delivery.query.filter_by(session_id=session.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Удалено поставок: {count}'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при очистке поставок: {str(e)}'}), 500
