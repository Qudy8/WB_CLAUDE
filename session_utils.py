"""
Session utility functions for checking permissions and session access.
"""

from flask import jsonify, current_app
from flask_login import current_user
from models import Session, SessionMember


def get_current_session():
    """
    Get current user's active session.
    Returns (session, error_response, status_code).
    If session is None, return the error response to the client.
    """
    if not current_user.active_session_id:
        return None, jsonify({'error': 'Нет активной сессии. Создайте или присоединитесь к сессии.'}), 400

    session = Session.query.get(current_user.active_session_id)
    if not session:
        return None, jsonify({'error': 'Активная сессия не найдена'}), 404

    return session, None, None


def get_user_role_in_session(session_id, user_id):
    """Get user's role in a specific session."""
    membership = SessionMember.query.filter_by(
        session_id=session_id,
        user_id=user_id
    ).first()
    return membership.role if membership else None


def check_session_permission(session_id=None, required_roles=None):
    """
    Check if current user has permission to access session.

    Args:
        session_id: Session ID to check. If None, uses current active session.
        required_roles: List of roles that have permission. If None, any member has access.

    Returns:
        (session, error_response, status_code)
        If session is None, return the error response to the client.
    """
    if session_id is None:
        # Use current active session
        return get_current_session()

    session = Session.query.get(session_id)
    if not session:
        return None, jsonify({'error': 'Сессия не найдена'}), 404

    # Check if user is a member
    role = get_user_role_in_session(session_id, current_user.id)
    if not role:
        return None, jsonify({'error': 'Вы не являетесь участником этой сессии'}), 403

    # Check role permissions if required
    if required_roles and role not in required_roles:
        return None, jsonify({'error': 'Недостаточно прав для этого действия'}), 403

    return session, None, None


def require_active_session():
    """
    Decorator-compatible function to check if user has active session.
    Use this at the start of route handlers.

    Usage:
        session, error, code = require_active_session()
        if error:
            return error, code
    """
    return get_current_session()


def check_modify_permission():
    """
    Check if current user has permission to modify data in their active session.
    Members with role 'member' can only view data, not modify it.

    Returns:
        (session, error_response, status_code)
        If session is None, return the error response to the client.

    Usage:
        session, error, code = check_modify_permission()
        if error:
            return error, code
    """
    # First check if user has an active session
    session, error, code = get_current_session()
    if error:
        return None, error, code

    # Get user's role in the session
    role = get_user_role_in_session(session.id, current_user.id)
    if not role:
        return None, jsonify({'error': 'Вы не являетесь участником этой сессии'}), 403

    # Check if role allows modifications
    # 'member' role is read-only, all other roles can modify
    if role == 'member':
        return None, jsonify({'error': 'У вас нет прав на изменение данных. Роль "Участник" предназначена только для просмотра.'}), 403

    return session, None, None


def check_section_permission(section):
    """
    Check if current user has permission to modify data in a specific section.
    Different roles have access to different sections.

    Args:
        section: Section name (e.g., 'labels', 'orders', 'production', 'boxes',
                'products', 'deliveries', 'inventory', 'finished_goods', 'defects', 'print_tasks')

    Returns:
        (session, error_response, status_code)
        If session is None, return the error response to the client.

    Usage:
        session, error, code = check_section_permission('labels')
        if error:
            return error, code
    """
    # Define which roles can modify which sections
    SECTION_PERMISSIONS = {
        'products': ['owner', 'admin', 'warehouse_manager', 'production_manager'],
        'labels': ['owner', 'admin', 'wb_manager', 'warehouse_manager', 'production_manager'],
        'orders': ['owner', 'admin', 'wb_manager'],
        'production': ['owner', 'admin', 'wb_manager', 'warehouse_manager', 'production_manager'],
        'production_orders': ['owner', 'admin', 'wb_manager', 'warehouse_manager', 'production_manager'],
        'boxes': ['owner', 'admin', 'wb_manager', 'warehouse_manager', 'production_manager'],
        'deliveries': ['owner', 'admin', 'warehouse_manager', 'production_manager'],
        'inventory': ['owner', 'admin'],
        'finished_goods': ['owner', 'admin', 'warehouse_manager', 'production_manager'],
        'defects': ['owner', 'admin', 'warehouse_manager', 'production_manager'],
        'print_tasks': ['owner', 'admin', 'warehouse_manager', 'production_manager'],
        'brand_expenses': ['owner', 'admin'],
    }

    # Human-readable section names in Russian
    SECTION_NAMES = {
        'products': 'Группы товаров',
        'labels': 'CIS этикетки',
        'orders': 'Заказы',
        'production': 'Производство',
        'production_orders': 'Заказы производство',
        'boxes': 'Коробки',
        'deliveries': 'Поставки',
        'inventory': 'Остатки материалов',
        'finished_goods': 'Готовая продукция',
        'defects': 'Брак',
        'print_tasks': 'Задачи печати',
        'brand_expenses': 'Расход на бренд',
    }

    # Role names in Russian
    ROLE_NAMES = {
        'owner': 'Владелец',
        'admin': 'Администратор',
        'member': 'Участник',
        'wb_manager': 'Менеджер кабинета WB',
        'warehouse_manager': 'Менеджер склада',
        'production_manager': 'Менеджер производства',
    }

    # First check if user has an active session
    session, error, code = get_current_session()
    if error:
        return None, error, code

    # Get user's role in the session
    role = get_user_role_in_session(session.id, current_user.id)
    if not role:
        return None, jsonify({'error': 'Вы не являетесь участником этой сессии'}), 403

    section_name = SECTION_NAMES.get(section, section)

    # Member role is always read-only
    if role == 'member':
        return None, jsonify({'error': f'У вас нет прав на изменение данных в разделе "{section_name}". Роль "Участник" предназначена только для просмотра.'}), 403

    # Check if role has permission for this section
    allowed_roles = SECTION_PERMISSIONS.get(section, ['owner', 'admin'])
    if role not in allowed_roles:
        allowed_roles_ru = [ROLE_NAMES.get(r, r) for r in allowed_roles]
        return None, jsonify({'error': f'У вас нет прав на изменение данных в разделе "{section_name}". Требуется одна из ролей: {", ".join(allowed_roles_ru)}.'}), 403

    return session, None, None


def check_wb_cabinet_permission(entity):
    """
    Check if current user's WB API key matches the one used to create this entity.
    This allows users to edit only data from their own WB cabinet, even if working in a shared session.

    Args:
        entity: Database entity with wb_api_key_hash field (ProductGroup, Order, etc.)

    Returns:
        (is_allowed: bool, error_response, status_code)
        If is_allowed is False, return the error response to the client.

    Usage:
        allowed, error, code = check_wb_cabinet_permission(product_group)
        if not allowed:
            return error, code
    """
    # Owner and admin can edit any data regardless of cabinet
    session, error, code = get_current_session()
    if error:
        return False, error, code

    role = get_user_role_in_session(session.id, current_user.id)
    if role in ['owner', 'admin']:
        return True, None, None

    # Check if entity has wb_api_key_hash field
    if not hasattr(entity, 'wb_api_key_hash'):
        # If entity doesn't track cabinet, allow modification based on section permissions only
        return True, None, None

    # If entity has no hash (created before this feature), allow modification
    if not entity.wb_api_key_hash:
        return True, None, None

    # Get current user's API key hash
    current_hash = current_user.get_wb_api_key_hash(current_app.config['ENCRYPTION_KEY'])
    if not current_hash:
        return False, jsonify({'error': 'API ключ не настроен. Настройте API ключ в разделе Настройки.'}), 400

    # Check if hashes match
    if current_hash != entity.wb_api_key_hash:
        return False, jsonify({
            'error': 'Вы не можете редактировать данные из другого кабинета Wildberries. '
                     'Эти данные были созданы с другим API ключом. '
                     'Для редактирования смените API ключ в настройках на тот, с которым были созданы эти данные.'
        }), 403

    return True, None, None
