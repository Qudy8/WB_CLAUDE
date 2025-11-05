"""Routes for product management."""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, ProductGroup, Product
from wb_api import WildberriesAPI
from config import Config
from session_utils import get_current_session, check_section_permission, check_wb_cabinet_permission

products_bp = Blueprint('products', __name__, url_prefix='/products')


@products_bp.route('/')
@login_required
def index():
    """Products main page."""
    session, error, code = get_current_session()
    if error:
        return error, code

    groups = ProductGroup.query.filter_by(session_id=session.id).order_by(ProductGroup.created_at.desc()).all()

    # Get current user's role in this session
    from session_utils import get_user_role_in_session
    user_role = get_user_role_in_session(session.id, current_user.id)

    return render_template('products.html', groups=groups, user_role=user_role)


@products_bp.route('/groups/create', methods=['POST'])
@login_required
def create_group():
    """Create new product group."""
    session, error, code = check_section_permission('products')
    if error:
        return error, code

    try:
        data = request.get_json()
        group_name = data.get('name', '').strip()
        nm_ids = data.get('nm_ids', [])

        if not group_name:
            return jsonify({'success': False, 'error': 'Название группы не указано'}), 400

        if not nm_ids:
            return jsonify({'success': False, 'error': 'Не указаны артикулы товаров'}), 400

        # Convert to integers
        nm_ids = [int(nm_id) for nm_id in nm_ids]

        # Get API key
        api_key = current_user.get_wb_api_key(Config.ENCRYPTION_KEY)
        if not api_key:
            return jsonify({'success': False, 'error': 'API ключ не настроен'}), 400

        # Fetch products from WB API
        wb_api = WildberriesAPI(api_key)
        products_data = wb_api.get_products_by_nmids(nm_ids)

        # Get API key hash for cabinet identification
        api_key_hash = current_user.get_wb_api_key_hash(Config.ENCRYPTION_KEY)

        # Create group
        group = ProductGroup(
            user_id=current_user.id,
            session_id=session.id,
            name=group_name,
            wb_api_key_hash=api_key_hash
        )
        db.session.add(group)
        db.session.flush()  # Get group ID

        # Create products
        for nm_id, card_data in products_data.items():
            if card_data is None:
                continue

            product = Product(
                group_id=group.id,
                nm_id=nm_id,
                vendor_code=card_data.get('vendorCode', ''),
                title=card_data.get('title', ''),
                brand=card_data.get('brand', ''),
                description=card_data.get('description', '')
            )

            # Save photos and sizes as JSON
            product.set_photos(card_data.get('photos', []))
            product.set_sizes(card_data.get('sizes', []))
            product.set_card_data(card_data)

            db.session.add(product)

        db.session.commit()

        return jsonify({'success': True, 'group_id': group.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@products_bp.route('/groups/<int:group_id>')
@login_required
def get_group(group_id):
    """Get group details."""
    session, error, code = get_current_session()
    if error:
        return error, code

    group = ProductGroup.query.filter_by(id=group_id, session_id=session.id).first_or_404()

    return jsonify({
        'id': group.id,
        'name': group.name,
        'products': [{'nm_id': p.nm_id, 'title': p.title} for p in group.products]
    })


@products_bp.route('/groups/<int:group_id>/content')
@login_required
def get_group_content(group_id):
    """Get group content grouped by sizes."""
    session, error, code = get_current_session()
    if error:
        return error, code

    group = ProductGroup.query.filter_by(id=group_id, session_id=session.id).first_or_404()

    size_groups = group.get_products_by_size()

    # Convert to JSON-serializable format
    result = {}
    for tech_size, items in size_groups.items():
        result[tech_size] = [
            {
                'product': item['product'].to_dict(),
                'size_info': item['size_info']
            }
            for item in items
        ]

    return jsonify({
        'group_id': group.id,
        'group_name': group.name,
        'sizes': result
    })


@products_bp.route('/groups/<int:group_id>/edit', methods=['POST'])
@login_required
def edit_group(group_id):
    """Edit existing product group."""
    session, error, code = check_section_permission('products')
    if error:
        return error, code

    try:
        group = ProductGroup.query.filter_by(id=group_id, session_id=session.id).first_or_404()

        # Check if user has permission to edit this group (based on WB cabinet)
        allowed, error, code = check_wb_cabinet_permission(group)
        if not allowed:
            return error, code

        data = request.get_json()
        group_name = data.get('name', '').strip()
        nm_ids = data.get('nm_ids', [])

        if not group_name:
            return jsonify({'success': False, 'error': 'Название группы не указано'}), 400

        if not nm_ids:
            return jsonify({'success': False, 'error': 'Не указаны артикулы товаров'}), 400

        # Convert to integers
        nm_ids = [int(nm_id) for nm_id in nm_ids]

        # Update group name
        group.name = group_name

        # Get current product nmIDs
        current_nm_ids = set(p.nm_id for p in group.products)
        new_nm_ids = set(nm_ids)

        # Remove products that are no longer in the list
        to_remove = current_nm_ids - new_nm_ids
        if to_remove:
            Product.query.filter(
                Product.group_id == group.id,
                Product.nm_id.in_(to_remove)
            ).delete(synchronize_session=False)

        # Add new products
        to_add = new_nm_ids - current_nm_ids
        if to_add:
            api_key = current_user.get_wb_api_key(Config.ENCRYPTION_KEY)
            if not api_key:
                return jsonify({'success': False, 'error': 'API ключ не настроен'}), 400

            wb_api = WildberriesAPI(api_key)
            products_data = wb_api.get_products_by_nmids(list(to_add))

            for nm_id, card_data in products_data.items():
                if card_data is None:
                    continue

                product = Product(
                    group_id=group.id,
                    nm_id=nm_id,
                    vendor_code=card_data.get('vendorCode', ''),
                    title=card_data.get('title', ''),
                    brand=card_data.get('brand', ''),
                    description=card_data.get('description', '')
                )

                product.set_photos(card_data.get('photos', []))
                product.set_sizes(card_data.get('sizes', []))
                product.set_card_data(card_data)

                db.session.add(product)

        db.session.commit()

        return jsonify({'success': True, 'group_id': group.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@products_bp.route('/groups/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    """Delete product group."""
    session, error, code = check_section_permission('products')
    if error:
        return error, code

    try:
        group = ProductGroup.query.filter_by(id=group_id, session_id=session.id).first_or_404()

        # Check if user has permission to delete this group (based on WB cabinet)
        allowed, error, code = check_wb_cabinet_permission(group)
        if not allowed:
            return error, code

        db.session.delete(group)
        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
