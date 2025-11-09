from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from cryptography.fernet import Fernet
import os
import json
from pypdf import PdfReader
from io import BytesIO
import random
import string
import hashlib

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model for authentication and settings."""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255))
    profile_pic = db.Column(db.String(500))

    # Business settings
    business_name = db.Column(db.String(255))
    wb_api_key_encrypted = db.Column(db.LargeBinary)
    ip_name = db.Column(db.String(500))  # ИП для этикеток

    # Label settings - what to show on labels (all True by default)
    label_show_ean = db.Column(db.Boolean, default=True)  # Показывать EAN-13 штрихкод
    label_show_gs1 = db.Column(db.Boolean, default=True)  # Показывать GS1 текст под DataMatrix
    label_show_title = db.Column(db.Boolean, default=True)  # Показывать название товара
    label_show_color = db.Column(db.Boolean, default=True)  # Показывать цвет
    label_show_size = db.Column(db.Boolean, default=True)  # Показывать размер
    label_show_material = db.Column(db.Boolean, default=True)  # Показывать состав
    label_show_country = db.Column(db.Boolean, default=True)  # Показывать страну
    label_show_ip = db.Column(db.Boolean, default=True)  # Показывать ИП
    label_show_article = db.Column(db.Boolean, default=True)  # Показывать артикул

    # Active session
    active_session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.email}>'

    def set_wb_api_key(self, api_key: str, encryption_key: str):
        """Encrypt and store Wildberries API key."""
        if not api_key:
            self.wb_api_key_encrypted = None
            return

        fernet = Fernet(encryption_key.encode())
        self.wb_api_key_encrypted = fernet.encrypt(api_key.encode())

    def get_wb_api_key(self, encryption_key: str) -> str:
        """Decrypt and return Wildberries API key."""
        if not self.wb_api_key_encrypted:
            return None

        fernet = Fernet(encryption_key.encode())
        return fernet.decrypt(self.wb_api_key_encrypted).decode()

    def has_wb_api_key(self) -> bool:
        """Check if user has saved WB API key."""
        return self.wb_api_key_encrypted is not None

    def get_wb_api_key_hash(self, encryption_key: str) -> str:
        """Get SHA256 hash of current WB API key for cabinet identification."""
        api_key = self.get_wb_api_key(encryption_key)
        if not api_key:
            return None
        return hashlib.sha256(api_key.encode()).hexdigest()

    def get_label_settings(self) -> dict:
        """Get label display settings as dictionary."""
        return {
            'show_ean': self.label_show_ean if self.label_show_ean is not None else True,
            'show_gs1': self.label_show_gs1 if self.label_show_gs1 is not None else True,
            'show_title': self.label_show_title if self.label_show_title is not None else True,
            'show_color': self.label_show_color if self.label_show_color is not None else True,
            'show_size': self.label_show_size if self.label_show_size is not None else True,
            'show_material': self.label_show_material if self.label_show_material is not None else True,
            'show_country': self.label_show_country if self.label_show_country is not None else True,
            'show_ip': self.label_show_ip if self.label_show_ip is not None else True,
            'show_article': self.label_show_article if self.label_show_article is not None else True,
        }


class Session(db.Model):
    """Session (Workspace) model for collaborative work."""

    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)  # Название сессии
    access_code = db.Column(db.String(6), unique=True, nullable=False, index=True)  # 6-значный код
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = db.relationship('User', foreign_keys=[owner_id], backref=db.backref('owned_sessions', lazy=True))
    members = db.relationship('SessionMember', backref='session', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Session {self.name} ({self.access_code})>'

    @staticmethod
    def generate_access_code():
        """Generate unique 6-character access code (letters + numbers)."""
        while True:
            # Generate random 6-character code (uppercase letters and digits)
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            # Check if code already exists
            if not Session.query.filter_by(access_code=code).first():
                return code

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'access_code': self.access_code,
            'owner_id': self.owner_id,
            'members_count': len(self.members),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class SessionMember(db.Model):
    """SessionMember model for user membership in sessions."""

    __tablename__ = 'session_members'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='member')  # owner, admin, member, wb_manager, warehouse_manager, production_manager

    # Timestamps
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('session_memberships', lazy=True, cascade='all, delete-orphan'))

    # Unique constraint: one user can have only one role in one session
    __table_args__ = (
        db.UniqueConstraint('session_id', 'user_id', name='_session_user_uc'),
    )

    def __repr__(self):
        return f'<SessionMember user_id={self.user_id} in session_id={self.session_id} as {self.role}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else None,
            'user_email': self.user.email if self.user else None,
            'role': self.role,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None
        }


class ProductGroup(db.Model):
    """Product group model for organizing WB products."""

    __tablename__ = 'product_groups'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)

    # WB Cabinet identification (SHA256 hash of API key used to create this group)
    wb_api_key_hash = db.Column(db.String(64), nullable=True, index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('product_groups', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('product_groups', lazy=True, cascade='all, delete-orphan'))
    products = db.relationship('Product', backref='group', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ProductGroup {self.name}>'

    def get_products_by_size(self):
        """Get products grouped by techSize."""
        size_groups = {}
        for product in self.products:
            for size in product.get_sizes():
                tech_size = size['techSize']
                if tech_size not in size_groups:
                    size_groups[tech_size] = []
                size_groups[tech_size].append({
                    'product': product,
                    'size_info': size
                })
        return dict(sorted(size_groups.items()))

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'products_count': len(self.products)
        }


class Product(db.Model):
    """Product model for storing WB product data."""

    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('product_groups.id'), nullable=False)

    # WB Product data
    nm_id = db.Column(db.BigInteger, nullable=False, index=True)
    vendor_code = db.Column(db.String(255))
    title = db.Column(db.String(500))
    brand = db.Column(db.String(255))
    description = db.Column(db.Text)

    # Photos (stored as JSON array)
    photos_json = db.Column(db.Text)

    # Sizes (stored as JSON array)
    sizes_json = db.Column(db.Text)

    # Full card data (stored as JSON for reference)
    card_data_json = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Product {self.nm_id}: {self.title}>'

    def get_photos(self):
        """Get photos as list."""
        if not self.photos_json:
            return []
        return json.loads(self.photos_json)

    def set_photos(self, photos):
        """Set photos from list."""
        self.photos_json = json.dumps(photos)

    def get_sizes(self):
        """Get sizes as list."""
        if not self.sizes_json:
            return []
        return json.loads(self.sizes_json)

    def set_sizes(self, sizes):
        """Set sizes from list."""
        self.sizes_json = json.dumps(sizes)

    def get_card_data(self):
        """Get full card data."""
        if not self.card_data_json:
            return {}
        return json.loads(self.card_data_json)

    def set_card_data(self, card_data):
        """Set full card data."""
        self.card_data_json = json.dumps(card_data)

    def get_thumbnail(self):
        """Get thumbnail URL (first photo, c246x328 size)."""
        photos = self.get_photos()
        if photos and len(photos) > 0:
            return photos[0].get('c246x328', photos[0].get('tm', ''))
        return None

    def get_main_image(self):
        """Get main image URL (first photo, c516x688 size)."""
        photos = self.get_photos()
        if photos and len(photos) > 0:
            return photos[0].get('c516x688', photos[0].get('big', ''))
        return None

    def get_metadata_for_labels(self):
        """Extract metadata for label generation from card data."""
        card_data = self.get_card_data()
        characteristics = card_data.get('characteristics', []) or []

        material = ""
        country = ""
        color = ""

        for ch in characteristics:
            name = (ch.get('name') or '').strip().lower()
            val = ch.get('value')

            if isinstance(val, list):
                val = ", ".join([str(v).strip() for v in val if v])
            val = str(val).strip() if val is not None else ""

            if not material and name in {'состав', 'материал', 'материал изделия'}:
                material = val
            if not country and name in {'страна', 'страна производства', 'страна-изготовитель',
                                       'страна производитель', 'country'}:
                country = val
            if not color and name in {'цвет', 'color'}:
                color = val

        return {
            'title': self.title or '',
            'material': material,
            'country': country,
            'color': color,
            'brand': self.brand or ''
        }

    def get_sku_for_size(self, tech_size: str):
        """Get SKU (barcode) for specific size."""
        sizes = self.get_sizes()
        for size in sizes:
            if str(size.get('techSize', '')).strip().lower() == tech_size.strip().lower():
                skus = size.get('skus', [])
                if skus:
                    return str(skus[0])
        return None

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'nm_id': self.nm_id,
            'vendor_code': self.vendor_code,
            'title': self.title,
            'brand': self.brand,
            'description': self.description,
            'thumbnail': self.get_thumbnail(),
            'main_image': self.get_main_image(),
            'sizes': self.get_sizes(),
            'photos': self.get_photos()
        }


class Order(db.Model):
    """Order model for managing customer orders."""

    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)

    # WB Cabinet identification (SHA256 hash of API key used to create this order)
    wb_api_key_hash = db.Column(db.String(64), nullable=True, index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('orders', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('orders', lazy=True, cascade='all, delete-orphan'))
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Order {self.name}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'items_count': len(self.items)
        }


class OrderItem(db.Model):
    """Order item model for individual products in orders."""

    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)

    # Product information (denormalized for order history)
    nm_id = db.Column(db.BigInteger, nullable=False, index=True)
    vendor_code = db.Column(db.String(255))
    brand = db.Column(db.String(255))
    title = db.Column(db.String(500))
    photo_url = db.Column(db.String(1000))

    # Size and color
    tech_size = db.Column(db.String(100))
    color = db.Column(db.String(255))

    # User editable fields
    quantity = db.Column(db.Integer, default=1)
    print_link = db.Column(db.String(1000))
    print_status = db.Column(db.String(255))
    priority = db.Column(db.String(100), default='НОРМАЛЬНЫЙ')

    # Checkbox selection
    selected = db.Column(db.Boolean, default=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<OrderItem {self.nm_id}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'order_id': self.order_id,
            'nm_id': self.nm_id,
            'vendor_code': self.vendor_code,
            'brand': self.brand,
            'title': self.title,
            'photo_url': self.photo_url,
            'tech_size': self.tech_size,
            'color': self.color,
            'quantity': self.quantity,
            'print_link': self.print_link,
            'print_status': self.print_status,
            'priority': self.priority,
            'selected': self.selected,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProductionItem(db.Model):
    """Production item model for items moved from orders to production."""

    __tablename__ = 'production_items'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    order_item_id = db.Column(db.Integer, nullable=True)  # Original order item ID for preserving order

    # Product information (copied from OrderItem)
    nm_id = db.Column(db.BigInteger, nullable=False, index=True)
    vendor_code = db.Column(db.String(255))
    brand = db.Column(db.String(255))
    title = db.Column(db.String(500))
    photo_url = db.Column(db.String(1000))

    # Size and color
    tech_size = db.Column(db.String(100))
    color = db.Column(db.String(255))

    # Fields from order (read-only in production)
    quantity = db.Column(db.Integer, default=1)
    print_link = db.Column(db.String(1000))
    print_status = db.Column(db.String(255))
    priority = db.Column(db.String(100), default='НОРМАЛЬНЫЙ')

    # New production-specific fields
    labels_link = db.Column(db.String(1000))  # КИЗЫ/ЭТИКЕТКИ
    box_number = db.Column(db.String(100))    # КОРОБ №
    selected = db.Column(db.Boolean, default=False)  # ВЫБРАТЬ

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('production_items', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('production_items', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProductionItem {self.nm_id}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'order_id': self.order_id,
            'nm_id': self.nm_id,
            'vendor_code': self.vendor_code,
            'brand': self.brand,
            'title': self.title,
            'photo_url': self.photo_url,
            'tech_size': self.tech_size,
            'color': self.color,
            'quantity': self.quantity,
            'print_link': self.print_link,
            'print_status': self.print_status,
            'priority': self.priority,
            'labels_link': self.labels_link,
            'box_number': self.box_number,
            'selected': self.selected,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CISLabel(db.Model):
    """CIS (Честный знак) label PDF files for product sizes."""

    __tablename__ = 'cis_labels'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('product_groups.id'), nullable=False)

    # Size identifier
    tech_size = db.Column(db.String(100), nullable=False)

    # File information
    filename = db.Column(db.String(500), nullable=False)
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_size = db.Column(db.Integer)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('cis_labels', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('cis_labels', lazy=True, cascade='all, delete-orphan'))
    group = db.relationship('ProductGroup', backref=db.backref('cis_labels', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<CISLabel {self.filename} for size {self.tech_size}>'

    def get_page_count(self):
        """Get number of pages in PDF file."""
        try:
            if not self.file_data:
                return 0

            pdf_stream = BytesIO(self.file_data)
            pdf_reader = PdfReader(pdf_stream)
            return len(pdf_reader.pages)
        except Exception as e:
            # If PDF is corrupted or can't be read, return 0
            return 0

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'tech_size': self.tech_size,
            'filename': self.filename,
            'file_size': self.file_size,
            'page_count': self.get_page_count(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Box(db.Model):
    """Box (Короб) model for organizing production items."""

    __tablename__ = 'boxes'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    box_number = db.Column(db.String(100), nullable=False)
    wb_box_id = db.Column(db.String(255))  # WB box ID (e.g., WB_1430965581)
    selected = db.Column(db.Boolean, default=False)  # Checkbox for selection

    # Delivery information
    delivery_number = db.Column(db.String(255))  # Номер поставки (e.g., WB-GI-180611768)
    warehouse = db.Column(db.String(255))  # Склад назначения (e.g., Псков)
    delivery_date = db.Column(db.String(50))  # Дата поставки (e.g., 24.09.2025)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('boxes', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('boxes', lazy=True, cascade='all, delete-orphan'))
    items = db.relationship('BoxItem', backref='box', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Box {self.box_number}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'box_number': self.box_number,
            'wb_box_id': self.wb_box_id,
            'selected': self.selected,
            'delivery_number': self.delivery_number,
            'warehouse': self.warehouse,
            'delivery_date': self.delivery_date,
            'items_count': len(self.items),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class BoxItem(db.Model):
    """Box item model for products in boxes."""

    __tablename__ = 'box_items'

    id = db.Column(db.Integer, primary_key=True)
    box_id = db.Column(db.Integer, db.ForeignKey('boxes.id'), nullable=False)

    # Product information
    nm_id = db.Column(db.BigInteger, nullable=False, index=True)
    tech_size = db.Column(db.String(100))
    barcode = db.Column(db.String(255))  # SKU/Barcode from WB API
    quantity = db.Column(db.Integer, default=1)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<BoxItem nm_id={self.nm_id} in Box {self.box_id}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'box_id': self.box_id,
            'nm_id': self.nm_id,
            'tech_size': self.tech_size,
            'barcode': self.barcode,
            'quantity': self.quantity,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Delivery(db.Model):
    """Delivery (Поставка) model for managing shipments."""

    __tablename__ = 'deliveries'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Delivery information
    delivery_date = db.Column(db.String(50))  # Дата поставки
    delivery_number = db.Column(db.String(255))  # Номер поставки
    status = db.Column(db.String(50), default='ГОТОВ')  # Статус: ГОТОВ, В АРХИВЕ
    warehouse = db.Column(db.String(255))  # Склад назначения

    # Barcodes (will be generated later)
    warehouse_box_barcode = db.Column(db.String(255))  # ШК КОРОБА СКЛАДА
    boxes_barcode = db.Column(db.String(255))  # ШК КОРОБОВ
    delivery_barcode = db.Column(db.String(255))  # ШК ПОСТАВКИ
    box_barcode = db.Column(db.String(255))  # ШК КОРОБА

    # Barcode PDF files
    box_barcode_pdf = db.Column(db.String(1000))  # Path to box barcodes PDF
    delivery_barcode_pdf = db.Column(db.String(1000))  # Path to delivery barcode PDF

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('deliveries', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('deliveries', lazy=True, cascade='all, delete-orphan'))
    boxes = db.relationship('DeliveryBox', backref='delivery', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Delivery {self.delivery_number}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'delivery_date': self.delivery_date,
            'delivery_number': self.delivery_number,
            'status': self.status,
            'warehouse': self.warehouse,
            'warehouse_box_barcode': self.warehouse_box_barcode,
            'boxes_barcode': self.boxes_barcode,
            'delivery_barcode': self.delivery_barcode,
            'box_barcode': self.box_barcode,
            'boxes_count': len(self.boxes),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DeliveryBox(db.Model):
    """DeliveryBox model for boxes in delivery."""

    __tablename__ = 'delivery_boxes'

    id = db.Column(db.Integer, primary_key=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('deliveries.id'), nullable=False)

    # Copy of box data (snapshot at the time of adding to delivery)
    box_number = db.Column(db.String(100))
    wb_box_id = db.Column(db.String(255))

    # Items data stored as JSON
    items_json = db.Column(db.Text)  # JSON array of box items

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DeliveryBox {self.box_number} in Delivery {self.delivery_id}>'

    def set_items(self, items_list):
        """Set items from list."""
        import json
        self.items_json = json.dumps(items_list, ensure_ascii=False)

    def get_items(self):
        """Get items as list."""
        import json
        if self.items_json:
            return json.loads(self.items_json)
        return []

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'delivery_id': self.delivery_id,
            'box_number': self.box_number,
            'wb_box_id': self.wb_box_id,
            'items': self.get_items(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PrintTask(db.Model):
    """Print task model for managing print orders."""

    __tablename__ = 'print_tasks'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id'), nullable=True)  # Reference to original OrderItem

    # Product information (denormalized from OrderItem)
    nm_id = db.Column(db.BigInteger, nullable=False, index=True)
    vendor_code = db.Column(db.String(255))
    brand = db.Column(db.String(255))
    title = db.Column(db.String(500))
    photo_url = db.Column(db.String(1000))

    # Size and color
    tech_size = db.Column(db.String(100))
    color = db.Column(db.String(255))

    # Print task fields
    quantity = db.Column(db.Integer, default=1)
    film_usage = db.Column(db.Float, default=0.0)  # РАСХОД ПЛЕНКИ в метрах
    print_link = db.Column(db.String(1000))
    print_status = db.Column(db.String(255))  # This field syncs with OrderItem
    priority = db.Column(db.String(100), default='НОРМАЛЬНЫЙ')

    # Checkbox selection
    selected = db.Column(db.Boolean, default=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('print_tasks', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('print_tasks', lazy=True, cascade='all, delete-orphan'))
    order_item = db.relationship('OrderItem', backref=db.backref('print_tasks', lazy=True))

    def __repr__(self):
        return f'<PrintTask {self.nm_id}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'order_item_id': self.order_item_id,
            'nm_id': self.nm_id,
            'vendor_code': self.vendor_code,
            'brand': self.brand,
            'title': self.title,
            'photo_url': self.photo_url,
            'tech_size': self.tech_size,
            'color': self.color,
            'quantity': self.quantity,
            'film_usage': self.film_usage,
            'print_link': self.print_link,
            'print_status': self.print_status,
            'priority': self.priority,
            'selected': self.selected,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Inventory(db.Model):
    """Inventory model for tracking supplies and materials."""

    __tablename__ = 'inventory'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Supplies quantities
    boxes_60x40x40 = db.Column(db.Integer, default=0)  # КОРОБ 60*40*40
    bags_25x30 = db.Column(db.Integer, default=0)  # ПАКЕТЫ 25*30
    print_film = db.Column(db.Integer, default=0)  # ПЛЕНКА ДЛЯ ПРИНТОВ

    # Paint colors
    paint_white = db.Column(db.Integer, default=0)  # КРАСКА БЕЛЫЙ
    paint_black = db.Column(db.Integer, default=0)  # КРАСКА ЧЕРНЫЙ
    paint_red = db.Column(db.Integer, default=0)  # КРАСКА КРАСНЫЙ
    paint_yellow = db.Column(db.Integer, default=0)  # КРАСКА ЖЕЛТЫЙ
    paint_blue = db.Column(db.Integer, default=0)  # КРАСКА СИНИЙ

    glue = db.Column(db.Integer, default=0)  # КЛЕЙ
    label_rolls = db.Column(db.Integer, default=0)  # ЭТИКЕТКИ РУЛ.

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('inventory', lazy=True, cascade='all, delete-orphan', uselist=False))
    user = db.relationship('User', backref=db.backref('inventory', lazy=True, cascade='all, delete-orphan', uselist=False))

    def __repr__(self):
        return f'<Inventory user_id={self.user_id}>'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'boxes_60x40x40': self.boxes_60x40x40,
            'bags_25x30': self.bags_25x30,
            'print_film': self.print_film,
            'paint_white': self.paint_white,
            'paint_black': self.paint_black,
            'paint_red': self.paint_red,
            'paint_yellow': self.paint_yellow,
            'paint_blue': self.paint_blue,
            'glue': self.glue,
            'label_rolls': self.label_rolls,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class FinishedGoodsStock(db.Model):
    """Finished goods stock model for tracking product inventory by sizes."""

    __tablename__ = 'finished_goods_stock'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_name = db.Column(db.String(500), nullable=False)
    color = db.Column(db.String(255))  # Цвет товара

    # Stock by sizes stored as JSON: {"XXS": 10, "XS": 20, "S": 30, ...}
    sizes_stock_json = db.Column(db.Text)

    # Defect quantities by sizes stored as JSON: {"XXS": 2, "XS": 1, "S": 0, ...}
    sizes_defect_json = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('finished_goods_stock', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('finished_goods_stock', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<FinishedGoodsStock {self.product_name}>'

    def get_sizes_stock(self):
        """Get sizes stock as dictionary."""
        if not self.sizes_stock_json:
            # Default sizes with 0 quantity
            return {
                'XXS': 0,
                'XS': 0,
                'S': 0,
                'M': 0,
                'L': 0,
                'XL': 0,
                'XXL': 0,
                'XXXL': 0
            }
        return json.loads(self.sizes_stock_json)

    def set_sizes_stock(self, sizes_dict):
        """Set sizes stock from dictionary."""
        self.sizes_stock_json = json.dumps(sizes_dict, ensure_ascii=False)

    def get_total_quantity(self):
        """Get total quantity across all sizes."""
        sizes = self.get_sizes_stock()
        return sum(sizes.values())

    def get_sizes_defect(self):
        """Get defect quantities as dictionary."""
        if not self.sizes_defect_json:
            # Default sizes with 0 defects
            return {
                'XXS': 0,
                'XS': 0,
                'S': 0,
                'M': 0,
                'L': 0,
                'XL': 0,
                'XXL': 0,
                'XXXL': 0
            }
        return json.loads(self.sizes_defect_json)

    def set_sizes_defect(self, sizes_dict):
        """Set defect quantities from dictionary."""
        self.sizes_defect_json = json.dumps(sizes_dict, ensure_ascii=False)

    def get_total_defect(self):
        """Get total defect quantity across all sizes."""
        sizes = self.get_sizes_defect()
        return sum(sizes.values())

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'product_name': self.product_name,
            'color': self.color,
            'sizes_stock': self.get_sizes_stock(),
            'total_quantity': self.get_total_quantity(),
            'sizes_defect': self.get_sizes_defect(),
            'total_defect': self.get_total_defect(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Defect(db.Model):
    """Defect model for tracking defective products by sizes."""

    __tablename__ = 'defects'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_name = db.Column(db.String(500), nullable=False)
    color = db.Column(db.String(255))  # Цвет товара

    # Defect quantities by sizes stored as JSON: {"XXS": 10, "XS": 20, "S": 30, ...}
    sizes_defect_json = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship('Session', backref=db.backref('defects', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('defects', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<Defect {self.product_name}>'

    def get_sizes_defect(self):
        """Get defect quantities as dictionary."""
        if not self.sizes_defect_json:
            # Default sizes with 0 quantity
            return {
                'XXS': 0,
                'XS': 0,
                'S': 0,
                'M': 0,
                'L': 0,
                'XL': 0,
                'XXL': 0,
                'XXXL': 0
            }
        return json.loads(self.sizes_defect_json)

    def set_sizes_defect(self, sizes_dict):
        """Set defect quantities from dictionary."""
        self.sizes_defect_json = json.dumps(sizes_dict, ensure_ascii=False)

    def get_total_defect(self):
        """Get total defect quantity across all sizes."""
        sizes = self.get_sizes_defect()
        return sum(sizes.values())

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'product_name': self.product_name,
            'color': self.color,
            'sizes_defect': self.get_sizes_defect(),
            'total_defect': self.get_total_defect(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
