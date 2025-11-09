"""
Sessions routes for managing collaborative workspaces.
"""

from flask import Blueprint, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Session, SessionMember, User
from functools import wraps

sessions_bp = Blueprint('sessions', __name__, url_prefix='/sessions')


# Helper functions for role checking
def get_user_role_in_session(session_id, user_id):
    """Get user's role in a session."""
    membership = SessionMember.query.filter_by(
        session_id=session_id,
        user_id=user_id
    ).first()
    return membership.role if membership else None


def require_session_role(required_roles):
    """Decorator to require specific role in session."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            session_id = kwargs.get('session_id')
            if not session_id:
                return jsonify({'error': 'Session ID required'}), 400

            role = get_user_role_in_session(session_id, current_user.id)
            if not role:
                return jsonify({'error': 'Вы не являетесь участником этой сессии'}), 403

            if role not in required_roles:
                return jsonify({'error': 'Недостаточно прав для этого действия'}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


@sessions_bp.route('/', methods=['GET'])
@login_required
def get_sessions():
    """Get all sessions where user is a member."""
    try:
        # Get all session memberships for current user
        memberships = SessionMember.query.filter_by(user_id=current_user.id).all()

        sessions_data = []
        for membership in memberships:
            session = membership.session
            sessions_data.append({
                'id': session.id,
                'name': session.name,
                'access_code': session.access_code,
                'role': membership.role,
                'is_owner': session.owner_id == current_user.id,
                'is_active': current_user.active_session_id == session.id,
                'members_count': len(session.members),
                'created_at': session.created_at.isoformat()
            })

        return jsonify({'sessions': sessions_data}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/current', methods=['GET'])
@login_required
def get_current_session():
    """Get current active session."""
    try:
        if not current_user.active_session_id:
            return jsonify({'error': 'Нет активной сессии'}), 404

        session = Session.query.get(current_user.active_session_id)
        if not session:
            return jsonify({'error': 'Сессия не найдена'}), 404

        # Get user's role
        membership = SessionMember.query.filter_by(
            session_id=session.id,
            user_id=current_user.id
        ).first()

        return jsonify({
            'session': {
                'id': session.id,
                'name': session.name,
                'access_code': session.access_code,
                'role': membership.role if membership else None,
                'is_owner': session.owner_id == current_user.id,
                'members_count': len(session.members),
                'created_at': session.created_at.isoformat()
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/create', methods=['POST'])
@login_required
def create_session():
    """Create a new session."""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()

        if not name:
            return jsonify({'error': 'Название сессии обязательно'}), 400

        # Generate unique access code
        access_code = Session.generate_access_code()

        # Create session
        session = Session(
            name=name,
            access_code=access_code,
            owner_id=current_user.id
        )
        db.session.add(session)
        db.session.flush()  # Get session.id

        # Create session membership with owner role
        membership = SessionMember(
            session_id=session.id,
            user_id=current_user.id,
            role='owner'
        )
        db.session.add(membership)

        # Set as active session
        current_user.active_session_id = session.id

        db.session.commit()

        return jsonify({
            'message': 'Сессия успешно создана',
            'session': {
                'id': session.id,
                'name': session.name,
                'access_code': session.access_code,
                'role': 'owner'
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/join', methods=['POST'])
@login_required
def join_session():
    """Join a session by access code."""
    try:
        data = request.get_json()
        access_code = data.get('access_code', '').strip().upper()

        if not access_code:
            return jsonify({'error': 'Код доступа обязателен'}), 400

        # Find session by access code
        session = Session.query.filter_by(access_code=access_code).first()
        if not session:
            return jsonify({'error': 'Сессия с таким кодом не найдена'}), 404

        # Check if user is already a member
        existing_membership = SessionMember.query.filter_by(
            session_id=session.id,
            user_id=current_user.id
        ).first()

        if existing_membership:
            # Just switch to this session
            current_user.active_session_id = session.id
            db.session.commit()
            return jsonify({
                'message': 'Вы уже участник этой сессии. Переключено на неё.',
                'session': {
                    'id': session.id,
                    'name': session.name,
                    'access_code': session.access_code,
                    'role': existing_membership.role
                }
            }), 200

        # Create new membership with 'member' role
        membership = SessionMember(
            session_id=session.id,
            user_id=current_user.id,
            role='member'
        )
        db.session.add(membership)

        # Set as active session
        current_user.active_session_id = session.id

        db.session.commit()

        return jsonify({
            'message': 'Вы успешно присоединились к сессии',
            'session': {
                'id': session.id,
                'name': session.name,
                'access_code': session.access_code,
                'role': 'member'
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/<int:session_id>/switch', methods=['POST'])
@login_required
def switch_session(session_id):
    """Switch to a different session."""
    try:
        # Check if user is a member of this session
        membership = SessionMember.query.filter_by(
            session_id=session_id,
            user_id=current_user.id
        ).first()

        if not membership:
            return jsonify({'error': 'Вы не являетесь участником этой сессии'}), 403

        # Switch active session
        current_user.active_session_id = session_id
        db.session.commit()

        return jsonify({'message': 'Сессия переключена успешно'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/<int:session_id>/leave', methods=['POST'])
@login_required
def leave_session(session_id):
    """Leave a session."""
    try:
        session = Session.query.get_or_404(session_id)

        # Owner cannot leave - must delete session instead
        if session.owner_id == current_user.id:
            return jsonify({'error': 'Владелец не может покинуть сессию. Используйте удаление сессии.'}), 400

        # Find membership
        membership = SessionMember.query.filter_by(
            session_id=session_id,
            user_id=current_user.id
        ).first()

        if not membership:
            return jsonify({'error': 'Вы не являетесь участником этой сессии'}), 404

        # Remove membership
        db.session.delete(membership)

        # If this was active session, clear it
        if current_user.active_session_id == session_id:
            # Try to switch to another session
            other_membership = SessionMember.query.filter_by(
                user_id=current_user.id
            ).filter(
                SessionMember.session_id != session_id
            ).first()

            if other_membership:
                current_user.active_session_id = other_membership.session_id
            else:
                current_user.active_session_id = None

        db.session.commit()

        return jsonify({'message': 'Вы успешно покинули сессию'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/<int:session_id>', methods=['GET'])
@login_required
def get_session(session_id):
    """Get session details."""
    try:
        session = Session.query.get_or_404(session_id)

        # Check if user is a member
        membership = SessionMember.query.filter_by(
            session_id=session_id,
            user_id=current_user.id
        ).first()

        if not membership:
            return jsonify({'error': 'Вы не являетесь участником этой сессии'}), 403

        return jsonify({
            'session': {
                'id': session.id,
                'name': session.name,
                'access_code': session.access_code,
                'owner_id': session.owner_id,
                'role': membership.role,
                'is_owner': session.owner_id == current_user.id,
                'is_active': current_user.active_session_id == session_id,
                'members_count': len(session.members),
                'created_at': session.created_at.isoformat()
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/<int:session_id>/members', methods=['GET'])
@login_required
def get_session_members(session_id):
    """Get all members of a session."""
    from flask import render_template, request as flask_request

    try:
        session = Session.query.get_or_404(session_id)

        # Check if user is a member
        membership = SessionMember.query.filter_by(
            session_id=session_id,
            user_id=current_user.id
        ).first()

        if not membership:
            # Check if JSON requested
            if flask_request.accept_mimetypes.accept_json and not flask_request.accept_mimetypes.accept_html:
                return jsonify({'error': 'Вы не являетесь участником этой сессии'}), 403
            flash('Вы не являетесь участником этой сессии', 'error')
            return redirect(url_for('main.dashboard'))

        # Get all members
        members_data = []
        for member in session.members:
            members_data.append({
                'id': member.id,
                'user_id': member.user_id,
                'user_name': member.user.name,
                'user_email': member.user.email,
                'user_profile_pic': member.user.profile_pic,
                'role': member.role,
                'is_owner': session.owner_id == member.user_id,
                'joined_at': member.joined_at.isoformat()
            })

        # Check if JSON is explicitly requested
        if flask_request.accept_mimetypes.accept_json and not flask_request.accept_mimetypes.accept_html:
            return jsonify({'members': members_data}), 200

        # Otherwise return HTML page
        is_owner = session.owner_id == current_user.id
        is_admin = membership.role in ['owner', 'admin']

        return render_template('session_members.html',
                             session=session,
                             members=members_data,
                             is_owner=is_owner,
                             is_admin=is_admin)

    except Exception as e:
        if flask_request.accept_mimetypes.accept_json and not flask_request.accept_mimetypes.accept_html:
            return jsonify({'error': str(e)}), 500
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))


@sessions_bp.route('/<int:session_id>/members/<int:user_id>/update-role', methods=['POST'])
@login_required
@require_session_role(['owner', 'admin'])
def update_member_role(session_id, user_id):
    """Update a member's role (owner/admin only)."""
    try:
        data = request.get_json()
        new_role = data.get('role', '').strip()

        if new_role not in ['admin', 'member', 'wb_manager', 'warehouse_manager', 'production_manager']:
            return jsonify({'error': 'Недопустимая роль. Доступные роли: admin, member, wb_manager, warehouse_manager, production_manager'}), 400

        session = Session.query.get_or_404(session_id)

        # Cannot change owner's role
        if session.owner_id == user_id:
            return jsonify({'error': 'Нельзя изменить роль владельца'}), 400

        # Find membership
        membership = SessionMember.query.filter_by(
            session_id=session_id,
            user_id=user_id
        ).first()

        if not membership:
            return jsonify({'error': 'Пользователь не является участником этой сессии'}), 404

        # Update role
        membership.role = new_role
        db.session.commit()

        return jsonify({'message': 'Роль успешно обновлена'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/<int:session_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
@require_session_role(['owner', 'admin'])
def remove_member(session_id, user_id):
    """Remove a member from session (owner/admin only)."""
    try:
        session = Session.query.get_or_404(session_id)

        # Cannot remove owner
        if session.owner_id == user_id:
            return jsonify({'error': 'Нельзя удалить владельца из сессии'}), 400

        # Find membership
        membership = SessionMember.query.filter_by(
            session_id=session_id,
            user_id=user_id
        ).first()

        if not membership:
            return jsonify({'error': 'Пользователь не является участником этой сессии'}), 404

        # Remove membership
        db.session.delete(membership)

        # If user had this as active session, clear it
        user = User.query.get(user_id)
        if user and user.active_session_id == session_id:
            # Try to switch to another session
            other_membership = SessionMember.query.filter_by(
                user_id=user_id
            ).filter(
                SessionMember.session_id != session_id
            ).first()

            if other_membership:
                user.active_session_id = other_membership.session_id
            else:
                user.active_session_id = None

        db.session.commit()

        return jsonify({'message': 'Участник успешно удален из сессии'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    """Delete a session (owner and admin can delete)."""
    try:
        session = Session.query.get_or_404(session_id)

        # Get user's role in this session
        user_role = get_user_role_in_session(session_id, current_user.id)

        # Only owner and admin can delete
        if user_role not in ['owner', 'admin']:
            return jsonify({'error': 'Только владелец или администратор могут удалить сессию'}), 403

        # If this was active session for any users, clear it
        users_with_active = User.query.filter_by(active_session_id=session_id).all()
        for user in users_with_active:
            # Try to switch to another session
            other_membership = SessionMember.query.filter_by(
                user_id=user.id
            ).filter(
                SessionMember.session_id != session_id
            ).first()

            if other_membership:
                user.active_session_id = other_membership.session_id
            else:
                user.active_session_id = None

        # Delete session (cascade will delete members and all related data)
        db.session.delete(session)
        db.session.commit()

        return jsonify({'message': 'Сессия успешно удалена'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/<int:session_id>/update', methods=['POST'])
@login_required
@require_session_role(['owner', 'admin'])
def update_session(session_id):
    """Update session name (owner/admin only)."""
    try:
        data = request.get_json()
        new_name = data.get('name', '').strip()

        if not new_name:
            return jsonify({'error': 'Название сессии обязательно'}), 400

        session = Session.query.get_or_404(session_id)
        session.name = new_name
        db.session.commit()

        return jsonify({'message': 'Название сессии обновлено'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
