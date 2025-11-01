"""
Session utility functions for checking permissions and session access.
"""

from flask import jsonify
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
