from flask import Blueprint, render_template, request, jsonify, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, ProductGroup, CISLabel
from io import BytesIO

labels_bp = Blueprint('labels', __name__, url_prefix='/labels')


@labels_bp.route('/')
@login_required
def labels_page():
    """Labels page showing all product groups with their sizes."""
    groups = ProductGroup.query.filter_by(user_id=current_user.id).order_by(ProductGroup.created_at.desc()).all()

    # Prepare data for each group with sizes and labels
    groups_data = []
    for group in groups:
        sizes_data = group.get_products_by_size()

        # Get all CIS labels for this group
        labels = CISLabel.query.filter_by(group_id=group.id, user_id=current_user.id).all()
        labels_by_size = {label.tech_size: label for label in labels}

        groups_data.append({
            'group': group,
            'sizes': sizes_data,
            'labels_by_size': labels_by_size
        })

    return render_template('labels.html', groups_data=groups_data)


@labels_bp.route('/upload', methods=['POST'])
@login_required
def upload_label():
    """Upload CIS label PDF file for a specific group and size."""
    try:
        group_id = request.form.get('group_id', type=int)
        tech_size = request.form.get('tech_size', '').strip()

        if not group_id or not tech_size:
            return jsonify({'error': 'Не указана группа или размер'}), 400

        # Verify group belongs to user
        group = ProductGroup.query.filter_by(id=group_id, user_id=current_user.id).first()
        if not group:
            return jsonify({'error': 'Группа не найдена'}), 404

        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не загружен'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400

        # Validate PDF file
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Разрешены только PDF файлы'}), 400

        # Read file data
        file_data = file.read()
        file_size = len(file_data)

        # Check file size (max 10MB)
        if file_size > 10 * 1024 * 1024:
            return jsonify({'error': 'Размер файла не должен превышать 10 МБ'}), 400

        # Check if label already exists for this group and size
        existing_label = CISLabel.query.filter_by(
            group_id=group_id,
            tech_size=tech_size,
            user_id=current_user.id
        ).first()

        if existing_label:
            # Update existing label
            existing_label.filename = file.filename
            existing_label.file_data = file_data
            existing_label.file_size = file_size
            message = 'Этикетка успешно обновлена'
        else:
            # Create new label
            new_label = CISLabel(
                user_id=current_user.id,
                group_id=group_id,
                tech_size=tech_size,
                filename=file.filename,
                file_data=file_data,
                file_size=file_size
            )
            db.session.add(new_label)
            message = 'Этикетка успешно загружена'

        db.session.commit()
        return jsonify({'success': True, 'message': message})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при загрузке файла: {str(e)}'}), 500


@labels_bp.route('/view/<int:label_id>')
@login_required
def view_label(label_id):
    """View/download CIS label PDF file."""
    try:
        label = CISLabel.query.filter_by(id=label_id, user_id=current_user.id).first()
        if not label:
            flash('Этикетка не найдена', 'error')
            return redirect(url_for('labels.labels_page'))

        # Create BytesIO object from binary data
        pdf_data = BytesIO(label.file_data)
        pdf_data.seek(0)

        # Send file with inline display (opens in browser)
        return send_file(
            pdf_data,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=label.filename
        )

    except Exception as e:
        flash(f'Ошибка при открытии файла: {str(e)}', 'error')
        return redirect(url_for('labels.labels_page'))


@labels_bp.route('/download/<int:label_id>')
@login_required
def download_label(label_id):
    """Download CIS label PDF file."""
    try:
        label = CISLabel.query.filter_by(id=label_id, user_id=current_user.id).first()
        if not label:
            return jsonify({'error': 'Этикетка не найдена'}), 404

        # Create BytesIO object from binary data
        pdf_data = BytesIO(label.file_data)
        pdf_data.seek(0)

        # Send file as attachment (downloads)
        return send_file(
            pdf_data,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=label.filename
        )

    except Exception as e:
        return jsonify({'error': f'Ошибка при скачивании файла: {str(e)}'}), 500


@labels_bp.route('/delete/<int:label_id>', methods=['POST'])
@login_required
def delete_label(label_id):
    """Delete CIS label PDF file."""
    try:
        label = CISLabel.query.filter_by(id=label_id, user_id=current_user.id).first()
        if not label:
            return jsonify({'error': 'Этикетка не найдена'}), 404

        db.session.delete(label)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Этикетка успешно удалена'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при удалении этикетки: {str(e)}'}), 500
