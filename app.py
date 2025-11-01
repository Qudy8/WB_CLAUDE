from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
from config import Config
from models import db, User
from auth import auth_bp
import os

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'main.index'


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))


# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')

from products_routes import products_bp
app.register_blueprint(products_bp)

from orders_routes import orders_bp
app.register_blueprint(orders_bp)

from labels_routes import labels_bp
app.register_blueprint(labels_bp)

from production_routes import production_bp
app.register_blueprint(production_bp)

from boxes_routes import boxes_bp
app.register_blueprint(boxes_bp)

from deliveries_routes import deliveries_bp
app.register_blueprint(deliveries_bp)

from print_tasks_routes import print_tasks_bp
app.register_blueprint(print_tasks_bp)

from inventory_routes import inventory_bp
app.register_blueprint(inventory_bp)

from finished_goods_routes import finished_goods_bp
app.register_blueprint(finished_goods_bp)

from defects_routes import defects_bp
app.register_blueprint(defects_bp)


# Main routes
@app.route('/')
def index():
    """Home page - redirects to dashboard if authenticated."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard page."""
    from models import ProductGroup, Order, CISLabel, ProductionItem, Box, Delivery, PrintTask, FinishedGoodsStock
    groups = ProductGroup.query.filter_by(user_id=current_user.id).order_by(ProductGroup.created_at.desc()).all()
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    production_items = ProductionItem.query.filter_by(user_id=current_user.id).order_by(ProductionItem.order_item_id.asc()).all()
    boxes = Box.query.filter_by(user_id=current_user.id).order_by(Box.box_number.asc()).all()
    deliveries = Delivery.query.filter_by(user_id=current_user.id).order_by(Delivery.created_at.desc()).all()
    print_tasks = PrintTask.query.filter_by(user_id=current_user.id).order_by(PrintTask.id.asc()).all()
    finished_goods_stocks = FinishedGoodsStock.query.filter_by(user_id=current_user.id).order_by(FinishedGoodsStock.product_name.asc()).all()

    # Prepare labels data for each group with sizes
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

    return render_template('dashboard.html', groups=groups, orders=orders, groups_data=groups_data, production_items=production_items, boxes=boxes, deliveries=deliveries, print_tasks=print_tasks, finished_goods_stocks=finished_goods_stocks)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Settings page for user configuration."""
    if request.method == 'POST':
        business_name = request.form.get('business_name', '').strip()
        wb_api_key = request.form.get('wb_api_key', '').strip()
        ip_name = request.form.get('ip_name', '').strip()

        # Update business name
        if business_name:
            current_user.business_name = business_name

        # Update IP name
        if ip_name:
            current_user.ip_name = ip_name

        # Update API key if provided
        if wb_api_key:
            try:
                current_user.set_wb_api_key(wb_api_key, app.config['ENCRYPTION_KEY'])
                flash('Настройки успешно сохранены!', 'success')
            except Exception as e:
                flash(f'Ошибка при сохранении API ключа: {str(e)}', 'error')
                db.session.rollback()
                return render_template('settings.html')
        else:
            # If no new API key provided, just save other fields
            if business_name or ip_name:
                flash('Настройки успешно сохранены!', 'success')

        try:
            db.session.commit()
        except Exception as e:
            flash(f'Ошибка при сохранении настроек: {str(e)}', 'error')
            db.session.rollback()

        return redirect(url_for('main.settings'))

    return render_template('settings.html')


@app.route('/labels/<path:filename>')
@login_required
def serve_label(filename):
    """Serve generated label PDF files."""
    labels_dir = os.path.join('static', 'labels')
    return send_file(os.path.join(labels_dir, filename), mimetype='application/pdf')


@app.route('/barcodes/<path:filename>')
@login_required
def serve_barcode(filename):
    """Serve generated barcode PDF files."""
    barcodes_dir = os.path.join('static', 'barcodes')
    return send_file(os.path.join(barcodes_dir, filename), mimetype='application/pdf')


@app.route('/settings/delete-api-key', methods=['POST'])
@login_required
def delete_api_key():
    """Delete WB API key."""
    try:
        current_user.wb_api_key_encrypted = None
        db.session.commit()
        flash('API ключ успешно удален.', 'info')
    except Exception as e:
        flash(f'Ошибка при удалении API ключа: {str(e)}', 'error')
        db.session.rollback()

    return redirect(url_for('main.settings'))


# Register main routes as blueprint for cleaner URL routing
from flask import Blueprint

main_bp = Blueprint('main', __name__)
main_bp.add_url_rule('/', 'index', index)
main_bp.add_url_rule('/dashboard', 'dashboard', dashboard, methods=['GET'])
main_bp.add_url_rule('/settings', 'settings', settings, methods=['GET', 'POST'])
main_bp.add_url_rule('/settings/delete-api-key', 'delete_api_key', delete_api_key, methods=['POST'])

app.register_blueprint(main_bp)


# Create database tables
with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
