"""
Brand Expenses Routes Blueprint
Handles tracking of product usage by brand, grouped by date.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, BrandExpense
from session_utils import get_current_session, check_session_permission
from sqlalchemy import func, desc
from datetime import date

brand_expenses_bp = Blueprint('brand_expenses', __name__, url_prefix='/brand-expenses')


@brand_expenses_bp.route('/', methods=['GET'])
@login_required
def get_brand_expenses():
    """
    Get all brand expenses grouped by date and brand.
    Returns structure: {
        "2025-01-15": {
            "Nike": [
                {"id": 1, "product_name": "T-Shirt", "color": "Red", "sizes": {"S": 10, "M": 20}, ...},
                ...
            ],
            "Adidas": [...]
        },
        ...
    }
    """
    session, error, code = get_current_session()
    if error:
        return error, code

    # Get all brand expenses for this session, ordered by date descending
    expenses = BrandExpense.query.filter_by(
        session_id=session.id
    ).order_by(desc(BrandExpense.date)).all()

    # Group by date, then by brand
    grouped = {}
    for expense in expenses:
        date_str = expense.date.isoformat()
        if date_str not in grouped:
            grouped[date_str] = {}

        brand = expense.brand or 'Без бренда'
        if brand not in grouped[date_str]:
            grouped[date_str][brand] = []

        grouped[date_str][brand].append(expense.to_dict())

    return jsonify(grouped)


@brand_expenses_bp.route('/<int:id>', methods=['DELETE'])
@login_required
def delete_brand_expense(id):
    """Delete a brand expense record (admin only)."""
    session, error, code = check_session_permission('brand_expenses')
    if error:
        return error, code

    expense = BrandExpense.query.filter_by(id=id, session_id=session.id).first()
    if not expense:
        return jsonify({'error': 'Запись не найдена'}), 404

    try:
        db.session.delete(expense)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@brand_expenses_bp.route('/by-date/<date_str>', methods=['GET'])
@login_required
def get_expenses_by_date(date_str):
    """Get all brand expenses for a specific date."""
    session, error, code = get_current_session()
    if error:
        return error, code

    try:
        # Parse date string (YYYY-MM-DD format)
        expense_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'Неверный формат даты. Используйте YYYY-MM-DD'}), 400

    expenses = BrandExpense.query.filter_by(
        session_id=session.id,
        date=expense_date
    ).all()

    # Group by brand
    grouped = {}
    for expense in expenses:
        brand = expense.brand or 'Без бренда'
        if brand not in grouped:
            grouped[brand] = []
        grouped[brand].append(expense.to_dict())

    return jsonify(grouped)


@brand_expenses_bp.route('/summary', methods=['GET'])
@login_required
def get_summary():
    """Get summary statistics for brand expenses."""
    session, error, code = get_current_session()
    if error:
        return error, code

    # Get all expenses for this session
    expenses = BrandExpense.query.filter_by(session_id=session.id).all()

    # Calculate summary
    total_products = len(expenses)
    total_quantity = sum(expense.get_total_quantity() for expense in expenses)

    # Get unique dates count
    unique_dates = len(set(expense.date for expense in expenses))

    # Get unique brands count
    unique_brands = len(set(expense.brand for expense in expenses))

    return jsonify({
        'total_products': total_products,
        'total_quantity': total_quantity,
        'unique_dates': unique_dates,
        'unique_brands': unique_brands
    })
