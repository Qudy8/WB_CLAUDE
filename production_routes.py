from flask import Blueprint, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import db, OrderItem, ProductionItem, Product, CISLabel, ProductGroup, BrandExpense, Inventory
from label_generator import generate_labels_sync
from session_utils import get_current_session, check_section_permission
import os
from datetime import datetime, date
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from PIL import Image
import requests

production_bp = Blueprint('production', __name__, url_prefix='/production')


@production_bp.route('/move-to-production', methods=['POST'])
@login_required
def move_to_production():
    """Move selected order items to production and generate labels."""
    session, error, code = check_section_permission('production')
    if error:
        return error, code

    try:
        data = request.get_json()
        order_id = data.get('order_id')
        item_ids = data.get('item_ids', [])

        if not order_id or not item_ids:
            return jsonify({'error': 'Не указан заказ или товары'}), 400

        # Get selected order items
        order_items = OrderItem.query.filter(
            OrderItem.id.in_(item_ids),
            OrderItem.order_id == order_id
        ).all()

        if not order_items:
            return jsonify({'error': 'Товары не найдены'}), 404

        # Check that all items have "ГОТОВ" print status
        items_not_ready = [item for item in order_items if item.print_status != 'ГОТОВ']
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
        for item in order_items:
            key = (item.nm_id, item.tech_size)
            if key not in items_by_product:
                items_by_product[key] = []
            items_by_product[key].append(item)

        # Create labels directory
        labels_dir = os.path.join('static', 'labels')
        os.makedirs(labels_dir, exist_ok=True)

        moved_count = 0
        labels_generated = 0
        total_items_quantity = 0  # Track total quantity for bags inventory

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
                session_id=session.id,
                group_id=product_group.id,
                tech_size=tech_size
            ).first()

            if not cis_label or not cis_label.file_data:
                current_app.logger.warning(f"CIS label not found for nm_id={nm_id}, size={tech_size}, skipping group")
                continue

            source_pdf_path = None
            output_path = None
            updated_source_path = None
            try:
                # Save source PDF temporarily
                temp_dir = os.path.join('temp')
                os.makedirs(temp_dir, exist_ok=True)

                source_pdf_path = os.path.join(temp_dir, f'source_{nm_id}_{tech_size}.pdf')
                with open(source_pdf_path, 'wb') as f:
                    f.write(cis_label.file_data)

                # Generate labels
                ip_name = getattr(current_user, 'ip_name', '') or ''

                # Get user's label settings
                label_settings = current_user.get_label_settings()

                output_path, updated_source_path = generate_labels_sync(
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
                final_filename = f'labels_{order_id}_{nm_id}_{tech_size}_{timestamp}.pdf'
                final_path = os.path.join(labels_dir, final_filename)

                # Copy generated labels to static/labels
                import shutil
                shutil.copy(output_path, final_path)

                # Update source CIS label with used pages removed
                with open(updated_source_path, 'rb') as f:
                    cis_label.file_data = f.read()
                    cis_label.file_size = len(cis_label.file_data)
                db.session.commit()

                labels_url = f'/labels/{final_filename}'
                labels_generated += 1
                labels_generated_for_group = True

            except Exception as e:
                current_app.logger.error(f"Error generating labels for nm_id={nm_id}, size={tech_size}: {e}")
                continue
            finally:
                # Always clean up temp files, even if there was an error
                for path in [source_pdf_path, output_path, updated_source_path]:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception as cleanup_error:
                            current_app.logger.warning(f"Failed to cleanup temp file {path}: {cleanup_error}")

            # Move items to production ONLY if labels were successfully generated
            if labels_generated_for_group:
                # Get photo from Product (since only first size has photo in OrderItem)
                photo_url = product.get_main_image() if product else ''

                for order_item in items:
                    production_item = ProductionItem(
                        user_id=current_user.id,
                        session_id=session.id,
                        order_id=order_item.order_id,
                        order_item_id=order_item.id,
                        nm_id=order_item.nm_id,
                        vendor_code=order_item.vendor_code,
                        brand=order_item.brand,
                        title=order_item.title,
                        photo_url=photo_url,  # Use photo from Product
                        tech_size=order_item.tech_size,
                        color=order_item.color,
                        quantity=order_item.quantity,
                        print_link=order_item.print_link,
                        print_status=order_item.print_status,
                        priority=order_item.priority,
                        labels_link=labels_url  # Store generated labels URL
                    )
                    db.session.add(production_item)
                    db.session.delete(order_item)
                    moved_count += 1

                    # Track total quantity for bags inventory deduction
                    total_items_quantity += order_item.quantity

                    # Track brand expense (расход на бренд)
                    try:
                        today = date.today()
                        brand_name = order_item.brand or 'Без бренда'
                        product_name = order_item.title or 'Без названия'
                        color_name = order_item.color or ''

                        # Find existing BrandExpense record for today
                        expense = BrandExpense.query.filter_by(
                            session_id=session.id,
                            date=today,
                            brand=brand_name,
                            product_name=product_name,
                            color=color_name
                        ).first()

                        if expense:
                            # Update existing record - add quantity to size and bags used
                            sizes = expense.get_sizes()
                            current_qty = sizes.get(order_item.tech_size, 0)
                            sizes[order_item.tech_size] = current_qty + order_item.quantity
                            expense.set_sizes(sizes)
                            # Add bags used (1 bag per item)
                            expense.bags_used = (expense.bags_used or 0) + order_item.quantity
                        else:
                            # Create new record
                            expense = BrandExpense(
                                session_id=session.id,
                                user_id=current_user.id,
                                date=today,
                                brand=brand_name,
                                product_name=product_name,
                                color=color_name,
                                bags_used=order_item.quantity  # 1 bag per item
                            )
                            sizes = {order_item.tech_size: order_item.quantity}
                            expense.set_sizes(sizes)
                            db.session.add(expense)
                    except Exception as e:
                        current_app.logger.error(f"Error tracking brand expense: {e}")
                        # Don't fail the whole operation if expense tracking fails

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

        if moved_count == 0:
            return jsonify({
                'error': 'Ни один товар не был перенесён. Убедитесь что для выбранных товаров:\n' +
                        '1. Товар добавлен в группу товаров (вкладка Товары)\n' +
                        '2. Загружены этикетки КИЗ для нужных размеров (вкладка Этикетки)'
            }), 400

        message = f'Перемещено в производство: {moved_count} товар(ов)'
        if labels_generated > 0:
            message += f', сгенерировано этикеток: {labels_generated}'

        return jsonify({
            'success': True,
            'message': message
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in move_to_production: {e}")
        return jsonify({'error': f'Ошибка при перемещении в производство: {str(e)}'}), 500


@production_bp.route('/items', methods=['GET'])
@login_required
def get_production_items():
    """Get all production items for current session."""
    session, error, code = get_current_session()
    if error:
        return error, code

    try:
        items = ProductionItem.query.filter_by(session_id=session.id).order_by(ProductionItem.created_at.desc()).all()

        return jsonify({
            'success': True,
            'items': [item.to_dict() for item in items]
        })

    except Exception as e:
        return jsonify({'error': f'Ошибка при загрузке производства: {str(e)}'}), 500


@production_bp.route('/items/<int:item_id>/update', methods=['POST'])
@login_required
def update_production_item(item_id):
    """Update production item fields (labels_link, box_number, selected)."""
    session, error, code = check_section_permission('production')
    if error:
        return error, code

    try:
        item = ProductionItem.query.filter_by(id=item_id, session_id=session.id).first()
        if not item:
            return jsonify({'error': 'Товар не найден'}), 404

        data = request.get_json()

        # Only allow updating production-specific fields
        if 'labels_link' in data:
            item.labels_link = data['labels_link']
        if 'box_number' in data:
            item.box_number = data['box_number']
        if 'selected' in data:
            item.selected = data['selected']

        db.session.commit()

        return jsonify({'success': True, 'message': 'Товар обновлен'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при обновлении товара: {str(e)}'}), 500


@production_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_production_item(item_id):
    """Delete production item."""
    session, error, code = check_section_permission('production')
    if error:
        return error, code

    try:
        item = ProductionItem.query.filter_by(id=item_id, session_id=session.id).first()
        if not item:
            return jsonify({'error': 'Товар не найден'}), 404

        db.session.delete(item)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Товар удален из производства'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при удалении товара: {str(e)}'}), 500


@production_bp.route('/clear', methods=['POST'])
@login_required
def clear_production():
    """Clear all production items for current session."""
    session, error, code = check_section_permission('production')
    if error:
        return error, code

    try:
        # Get count before deletion
        count = ProductionItem.query.filter_by(session_id=session.id).count()

        if count == 0:
            return jsonify({'success': True, 'message': 'Производство уже пусто'})

        # Delete all production items for current session
        ProductionItem.query.filter_by(session_id=session.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Производство очищено. Удалено товаров: {count}'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing production: {e}")
        return jsonify({'error': f'Ошибка при очистке производства: {str(e)}'}), 500


@production_bp.route('/print-table', methods=['GET'])
@login_required
def print_production_table():
    """Generate PDF table with production items."""
    session, error, code = get_current_session()
    if error:
        return error, code

    try:
        # Get all production items for current session
        items = ProductionItem.query.filter_by(session_id=session.id).order_by(ProductionItem.order_item_id.asc()).all()

        if not items:
            return jsonify({'error': 'Нет товаров в производстве'}), 400

        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm)

        # Register Arial font if available
        try:
            pdfmetrics.registerFont(TTFont('Arial', 'fonts/Arial.ttf'))
            font_name = 'Arial'
        except:
            font_name = 'Helvetica'

        # Prepare data for table
        data = [['ФОТО', 'БРЕНД', 'АРТИКУЛ WB', 'РАЗМЕР', 'ЦВЕТ', 'КОЛ-ВО', 'КОРОБ №']]
        row_heights = [12*mm]  # Header row height

        # Track which nm_id already has photo shown (only first occurrence gets photo)
        nm_ids_with_photo = set()

        for item in items:
            # Download and resize image only for first occurrence of each nm_id
            img_cell = ''
            has_image = False

            # Show photo only if this nm_id hasn't been shown yet
            if item.photo_url and item.nm_id not in nm_ids_with_photo:
                img_data = None
                pil_img = None
                img_buffer = None
                try:
                    # Download image
                    response = requests.get(item.photo_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    if response.status_code == 200:
                        img_data = BytesIO(response.content)
                        pil_img = Image.open(img_data)

                        # Convert to RGB if needed
                        if pil_img.mode != 'RGB':
                            pil_img = pil_img.convert('RGB')

                        # Calculate aspect ratio and resize
                        max_size = 40 * mm  # Увеличил с 20mm до 40mm
                        aspect = pil_img.width / pil_img.height

                        if aspect > 1:  # Wider than tall
                            width = max_size
                            height = max_size / aspect
                        else:  # Taller than wide
                            height = max_size
                            width = max_size * aspect

                        # Resize with high quality
                        pil_img = pil_img.resize((int(width * 3), int(height * 3)), Image.Resampling.LANCZOS)

                        # Save to BytesIO as JPEG
                        img_buffer = BytesIO()
                        pil_img.save(img_buffer, format='JPEG', quality=85)
                        img_buffer.seek(0)

                        # Create ReportLab Image with actual dimensions
                        img_cell = RLImage(img_buffer, width=width, height=height)
                        has_image = True
                        nm_ids_with_photo.add(item.nm_id)  # Mark this nm_id as already shown
                        current_app.logger.info(f"Successfully loaded image for item {item.id}: {item.photo_url}")
                except Exception as e:
                    current_app.logger.error(f"Failed to load image for item {item.id} ({item.photo_url}): {e}")
                finally:
                    # Explicitly close resources to prevent memory leaks
                    if pil_img:
                        try:
                            pil_img.close()
                        except Exception:
                            pass
                    if img_data:
                        try:
                            img_data.close()
                        except Exception:
                            pass
                    # Note: img_buffer is kept open because ReportLab needs it for rendering

            row = [
                img_cell,
                item.brand or '',
                str(item.nm_id),
                item.tech_size or '',
                item.color or '',
                str(item.quantity or 1),
                item.box_number or ''
            ]
            data.append(row)

            # Set row height: 45mm for rows with images, minimal (10mm) for text-only rows
            if has_image:
                row_heights.append(45*mm)
            else:
                row_heights.append(10*mm)

        # Create table with dynamic row heights
        col_widths = [45*mm, 35*mm, 30*mm, 22*mm, 28*mm, 20*mm, 20*mm]  # Увеличенные размеры
        table = Table(data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)

        # Style the table - простой практичный стиль
        table.setStyle(TableStyle([
            # Header style
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 4),

            # Body style
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('TOPPADDING', (0, 1), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
            ('LEFTPADDING', (0, 1), (-1, -1), 3),
            ('RIGHTPADDING', (0, 1), (-1, -1), 3),

            # Grid
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        # Build PDF
        elements = []

        # Add title - простой стиль
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=font_name,
            fontSize=14,
            textColor=colors.black,
            spaceAfter=8,
            alignment=1  # Center
        )

        title = Paragraph(f'Производство - {datetime.now().strftime("%d.%m.%Y %H:%M")}', title_style)
        elements.append(title)
        elements.append(Spacer(1, 5*mm))
        elements.append(table)

        doc.build(elements)

        # Prepare file for download
        buffer.seek(0)
        filename = f'production_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'

        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"Error generating production PDF: {e}")
        return jsonify({'error': f'Ошибка при генерации PDF: {str(e)}'}), 500
