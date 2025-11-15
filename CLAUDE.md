# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask web application for Wildberries (Russian marketplace) seller operations. Main features: **Multi-user collaborative sessions**, Google OAuth authentication, encrypted API key storage, product group management, order management, CIS label generation, and production workflow tracking.

**Tech Stack:** Python 3.8+, Flask 3.0, SQLAlchemy, Flask-Login, Fernet encryption, PyMuPDF, ReportLab, pylibdmtx (DataMatrix), python-barcode (EAN-13)

**Multi-User Architecture:** Users can create or join collaborative sessions (workspaces) with role-based access control (owner/admin/member/wb_manager/warehouse_manager/production_manager). Sessions are identified by 6-character access codes. All data (products, orders, inventory, etc.) is isolated per session while user settings (API keys, business name) remain private.

## Development Setup

### Initial Setup

```bash
# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate secret key
python -c "import secrets; print(secrets.token_hex(32))"
```

Required environment variables:
- `SECRET_KEY`: Flask session security
- `DATABASE_URL`: Database connection (default: SQLite)
- `GOOGLE_CLIENT_ID`: OAuth client ID
- `GOOGLE_CLIENT_SECRET`: OAuth client secret
- `ENCRYPTION_KEY`: Fernet key for API key encryption

### Running the Application

```bash
# Development server
python app.py
# Runs on http://localhost:5000 with debug mode

# Production (example)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Database Management

Database is created automatically on first run via `db.create_all()` in app.py (search for `db.create_all()` call).

**First-time setup with sessions:**
```bash
# After database creation, run the migration script to add session support
python migrate_to_sessions.py
```

This script:
- Creates a session for each existing user
- Creates SessionMember with role='owner' for each user
- Sets active_session_id for each user
- Migrates all user data (products, orders, etc.) to their session

For Flask-Migrate (if needed):
```bash
flask db init
flask db migrate -m "Migration message"
flask db upgrade
```

## Architecture

### Blueprint Structure

Fourteen main blueprints handle routing:

1. **auth_bp** (auth.py) - Google OAuth flow
   - `/auth/login` - Initiates OAuth
   - `/auth/callback` - Handles OAuth callback
   - `/auth/logout` - Logs out user

2. **sessions_bp** (sessions_routes.py) - Session management
   - `/sessions/` - Get all user's sessions
   - `/sessions/current` - Get current active session
   - `/sessions/create` - Create new session (generates 6-char code)
   - `/sessions/join` - Join session by access code
   - `/sessions/<id>/switch` - Switch to different session
   - `/sessions/<id>/leave` - Leave session
   - `/sessions/<id>` - Get session details
   - `/sessions/<id>/members` - Get session members
   - `/sessions/<id>/members/<user_id>/update-role` - Update member role (owner/admin only)
   - `/sessions/<id>/members/<user_id>` DELETE - Remove member (owner/admin only)
   - `/sessions/<id>` DELETE - Delete session (owner/admin only)
   - `/sessions/<id>/update` - Update session name (owner/admin only)

3. **products_bp** (products_routes.py) - Product group management
   - `/products/` - Products page
   - `/products/groups/create` - Create group with WB products
   - `/products/groups/<id>` - Get group details
   - `/products/groups/<id>/content` - Get products grouped by size
   - `/products/groups/<id>/edit` - Edit group (add/remove products)
   - `/products/groups/<id>/delete` - Delete group

4. **orders_bp** (orders_routes.py) - Order management
   - `/orders/` - List all orders
   - `/orders/<id>` - Get order with items
   - `/orders/create` - Create order from WB products (creates OrderItem per size)
   - `/orders/<id>/items/<item_id>/update` - Update order item fields
   - `/orders/<id>/delete` - Delete order

5. **labels_bp** (labels_routes.py) - CIS label PDF management
   - `/labels/` - Labels page showing groups with sizes
   - `/labels/upload` - Upload CIS label PDF for specific group+size
   - `/labels/view/<id>` - View label PDF inline
   - `/labels/download/<id>` - Download label PDF
   - `/labels/delete/<id>` - Delete label

6. **production_orders_bp** (production_orders_routes.py) - Production Orders (staging between Orders and Production)
   - `/production-orders/` - Get all production orders
   - `/production-orders/move-to-production` - Move selected production orders to production + generate labels
   - `/production-orders/<id>/update` - Update production order fields
   - `/production-orders/<id>/delete` - Delete production order

7. **production_bp** (production_routes.py) - Production workflow
   - `/production/move-to-production` - Move selected order items to production + generate labels
   - `/production/items` - Get all production items
   - `/production/items/<id>/update` - Update production fields (labels_link, box_number, selected)
   - `/production/items/<id>/delete` - Delete production item

8. **print_tasks_bp** (print_tasks_routes.py) - Print task management
   - `/print-tasks/` - Get all print tasks
   - `/print-tasks/copy-from-order` - Copy selected order items to print tasks
   - `/print-tasks/<id>/update` - Update print task (film_usage, print_status, etc.)
   - `/print-tasks/<id>/delete` - Delete print task

9. **boxes_bp** (boxes_routes.py) - Box management
   - `/boxes/` - Get all boxes
   - `/boxes/add-from-production` - Create boxes from selected production items
   - `/boxes/<id>/update` - Update box fields (delivery info, wb_box_id, selected)
   - `/boxes/<id>/delete` - Delete box

10. **deliveries_bp** (deliveries_routes.py) - Delivery management
    - `/deliveries/` - Get all deliveries
    - `/deliveries/add-from-boxes` - Create delivery from selected boxes + generate barcodes
    - `/deliveries/<id>/update` - Update delivery status
    - `/deliveries/<id>/delete` - Delete delivery

11. **inventory_bp** (inventory_routes.py) - Inventory tracking
    - `/inventory/` - Inventory page
    - `/inventory/update` - Update inventory quantities (boxes, bags, film, paint, glue, labels)

12. **finished_goods_bp** (finished_goods_routes.py) - Finished goods stock management
    - `/finished-goods/` - Get all finished goods stocks
    - `/finished-goods/create` - Create new finished goods stock item
    - `/finished-goods/<id>/update` - Update stock quantities by size
    - `/finished-goods/<id>/delete` - Delete stock item

13. **defects_bp** (defects_routes.py) - Defect tracking
    - `/defects/` - Get all defects
    - `/defects/create` - Create new defect entry
    - `/defects/<id>/update` - Update defect quantities by size
    - `/defects/<id>/delete` - Delete defect entry

14. **brand_expenses_bp** (brand_expenses_routes.py) - Brand expense tracking
    - `/brand-expenses/` - Get all brand expenses grouped by date and brand
    - `/brand-expenses/create` - Create new brand expense entry
    - `/brand-expenses/<id>/update` - Update brand expense
    - `/brand-expenses/<id>/delete` - Delete brand expense

15. **main_bp** (app.py) - Core pages
    - `/` - Login page or redirect to dashboard
    - `/dashboard` - Main dashboard (shows all entities: groups, orders, production orders, production items, boxes, deliveries, print tasks, finished goods, brand expenses)
    - `/settings` - API key and business configuration (business_name, wb_api_key, ip_name)
    - `/settings/delete-api-key` - Delete WB API key
    - `/labels/<filename>` - Serve generated label PDFs

### Data Models (models.py)

**Session** (NEW)
- Collaborative workspace for multiple users
- Fields: name, access_code (6-char unique code), owner_id
- Methods: `generate_access_code()` - generates unique 6-character code (uppercase letters + digits)
- Relationships: One-to-many with SessionMember, ProductGroup, Order, ProductionItem, CISLabel, Box, Delivery, PrintTask, Inventory, FinishedGoodsStock, Defect (all cascade delete)
- **Data Isolation:** All session data is completely isolated - users only see data from their active session

**SessionMember** (NEW)
- Links users to sessions with roles
- Fields: session_id, user_id, role ('owner'/'admin'/'member'/'wb_manager'/'warehouse_manager'/'production_manager'), joined_at
- Unique constraint: one user can have only one role per session
- Methods: `to_dict()` - includes user info and role
- **Roles (текущая реализация):**
  - `owner`: Владелец - полный контроль над сессией
    - ✅ Удаление сессии (DELETE /sessions/:id)
    - ✅ Управление всеми участниками (изменение ролей, удаление)
    - ✅ Изменение настроек сессии (название)
    - ✅ Все операции с данными (products, orders, production, boxes, deliveries, inventory)

  - `admin`: Администратор - полный контроль над сессией (как owner)
    - ✅ Удаление сессии (DELETE /sessions/:id)
    - ✅ Управление всеми участниками (изменение ролей, удаление)
    - ✅ Изменение настроек сессии (название)
    - ✅ Все операции с данными (products, orders, production, boxes, deliveries, inventory)

  - `member`: Участник - только просмотр (read-only)
    - ✅ Просмотр всех данных (products, orders, production, boxes, deliveries, inventory)
    - ❌ Не может создавать, изменять или удалять данные
    - ❌ Не может управлять участниками
    - ❌ Не может изменять настройки сессии
    - ❌ Не требуется настройка API ключа Wildberries

  - `wb_manager`: Менеджер кабинета WB
    - ✅ Редактирование: labels, orders, production, boxes
    - ✅ Просмотр всех остальных разделов (products, deliveries, inventory, finished_goods, defects, print_tasks)
    - ❌ Не может редактировать: products (группы товаров), deliveries, inventory, finished_goods, defects, print_tasks
    - ❌ Не может управлять участниками
    - ❌ Не может изменять настройки сессии

  - `warehouse_manager`: Менеджер склада
    - ✅ Редактирование: deliveries, inventory, finished_goods, boxes
    - ✅ Просмотр всех остальных разделов (products, orders, production, labels, defects, print_tasks)
    - ❌ Не может редактировать: products, orders, production, labels, defects, print_tasks
    - ❌ Не может управлять участниками
    - ❌ Не может изменять настройки сессии

  - `production_manager`: Менеджер производства
    - ✅ Редактирование: production, defects, print_tasks
    - ✅ Просмотр всех остальных разделов (products, orders, labels, boxes, deliveries, inventory, finished_goods)
    - ❌ Не может редактировать: products, orders, labels, boxes, deliveries, inventory, finished_goods
    - ❌ Не может управлять участниками
    - ❌ Не может изменять настройки сессии

- **Примечание:** Разграничение прав реализовано через функцию `check_section_permission()` в session_utils.py, которая проверяет права доступа для каждого раздела отдельно

**User**
- Google OAuth identity (google_id, email, name, profile_pic)
- Business settings (business_name, wb_api_key_encrypted, ip_name) - **private per user**
- Active session: active_session_id - tracks which session user is currently working in
- Methods: `set_wb_api_key()`, `get_wb_api_key()`, `has_wb_api_key()`
- Relationships: One-to-many with owned_sessions, session_memberships
- **Note:** User can be in multiple sessions but only one is active at a time

**ProductGroup**
- Links to Session via session_id (for data filtering) and User via user_id (for tracking creator)
- Contains multiple Product entries
- Methods: `get_products_by_size()` - groups products by techSize, `to_dict()`
- Relationships: Belongs to Session, many Products (cascade delete), many CISLabels

**Product**
- Stores WB product data (nm_id, vendor_code, title, brand, description)
- JSON fields: photos_json, sizes_json, card_data_json (full WB API response)
- Methods:
  - Image helpers: `get_thumbnail()`, `get_main_image()`
  - `get_metadata_for_labels()` - extracts material, country, color from characteristics
  - `get_sku_for_size()` - returns barcode for specific techSize
  - JSON serialization helpers

**Order**
- User-created orders with name and timestamp
- Relationships: One-to-many with OrderItem (cascade delete)

**OrderItem**
- Individual product size entries in an order
- Denormalized product data (nm_id, vendor_code, brand, title, photo_url, tech_size, color)
- User-editable fields: quantity, print_link, print_status, priority, selected
- Created one per size for each product in order

**ProductionOrder**
- Staging area between Orders and Production (intermediate step)
- Denormalized product data similar to OrderItem
- Fields: nm_id, vendor_code, brand, title, photo_url, tech_size, color, quantity
- User-editable: quantity, selected
- Can be moved to production with label generation
- Preserves order_item_id for tracking original source

**ProductionItem**
- Items moved from OrderItem or ProductionOrder to production
- Copies all OrderItem fields + adds: labels_link, box_number, selected
- Preserves order_item_id for maintaining original sort order
- order_id nullable (allows independent production items)

**CISLabel**
- Stores CIS (Честный знак) label PDF files per group+techSize
- Binary storage: file_data (LargeBinary), file_size
- Methods: `get_page_count()` - reads PDF page count using pypdf
- Used as source DataMatrix for label generation

**PrintTask**
- Copy of OrderItem for print workflow management
- Denormalized product data (nm_id, vendor_code, brand, title, photo_url, tech_size, color)
- Print-specific fields: film_usage (float), print_link, print_status, priority
- References original OrderItem via order_item_id
- Checkbox selection for bulk operations

**Box**
- Container for organizing production items by box number
- Fields: box_number, wb_box_id (from WB API), selected
- Delivery info: delivery_number, warehouse, delivery_date
- Relationships: One-to-many with BoxItem (cascade delete)

**BoxItem**
- Individual products within a box
- Fields: nm_id, tech_size, barcode (SKU from WB), quantity
- Belongs to Box via box_id

**Delivery**
- Shipment/delivery tracking (Поставка)
- Fields: delivery_date, delivery_number, status, warehouse
- Barcode fields: warehouse_box_barcode, boxes_barcode, delivery_barcode, box_barcode
- Barcode PDF paths: box_barcode_pdf, delivery_barcode_pdf
- Relationships: One-to-many with DeliveryBox (cascade delete)

**DeliveryBox**
- Snapshot of box data when added to delivery
- Fields: box_number, wb_box_id, items_json (JSON array of box items)
- Methods: `set_items()`, `get_items()` - JSON serialization helpers

**Inventory**
- Tracks supplies and materials (one record per user)
- Supplies: boxes_60x40x40, bags_25x30, print_film, label_rolls
- Paint colors: paint_white, paint_black, paint_red, paint_yellow, paint_blue
- Other: glue
- One-to-one relationship with User

**FinishedGoodsStock**
- Tracks finished product inventory by size
- Fields: product_name, color, sizes_stock_json, sizes_defect_json
- Stores size quantities as JSON: {"XXS": 10, "XS": 20, "S": 30, ...}
- Defect tracking integrated: sizes_defect_json stores defective quantities
- Methods: `get_sizes_stock()`, `set_sizes_stock()`, `get_total_quantity()`, `get_sizes_defect()`, `set_sizes_defect()`

**Defect**
- Tracks defective products separately by size
- Fields: product_name, color, sizes_defect_json
- Similar structure to FinishedGoodsStock but specifically for defects
- Methods: `get_sizes_defect()`, `set_sizes_defect()`, `get_total_defects()`

**BrandExpense**
- Tracks product usage and material consumption by brand and date
- Fields: date, brand, product_name, color, sizes_json (quantities by size)
- Material tracking: boxes_used, bags_used, film_used, paint_used, glue_used, labels_used
- Grouped by date and brand for expense analysis
- Methods: `get_sizes()`, `set_sizes()` - JSON serialization helpers
- Used for cost tracking and reporting per brand

### Security Implementation

**API Key Encryption:**
- Uses Fernet symmetric encryption (cryptography library)
- Encryption key stored in ENCRYPTION_KEY env var
- API keys encrypted before database storage in User.set_wb_api_key()
- Decrypted on-demand via User.get_wb_api_key()

**OAuth Flow:**
- State parameter prevents CSRF attacks
- ID tokens verified with Google's public keys
- HttpOnly, SameSite=Lax cookies

**Database Access:**
- All queries filtered by current_user.active_session_id (session-based isolation)
- No raw SQL execution
- Cascade deletes prevent orphaned records
- Session deletion cascades to all session data (products, orders, inventory, etc.)

**Session Management & Data Isolation:**
- Each user must have an active session to access data
- All data queries filter by `session_id` (not user_id) for multi-user collaboration
- User settings (API keys, business name) remain private per user
- Helper module `session_utils.py` provides:
  - `get_current_session()` - retrieves and validates active session
  - `get_user_role_in_session()` - checks user's role in session
  - `check_session_permission()` - validates session access and role permissions (generic)
  - `check_modify_permission()` - validates modify permissions (blocks 'member' role from any modifications)
  - `check_section_permission(section)` - validates section-specific permissions based on role
    - Section-based access control for specialized roles (wb_manager, warehouse_manager, production_manager)
    - Allows fine-grained control over which roles can edit which sections
- All routes use session validation pattern:
  ```python
  from session_utils import get_current_session, check_section_permission

  # For read-only routes
  @route('/endpoint', methods=['GET'])
  @login_required
  def handler():
      session, error, code = get_current_session()
      if error:
          return error, code

      # Query data by session_id
      items = Model.query.filter_by(session_id=session.id).all()

  # For modification routes
  @route('/endpoint', methods=['POST'])
  @login_required
  def handler():
      session, error, code = check_section_permission('orders')
      if error:
          return error, code

      # Perform modification
  ```

### External API Integration (wb_api.py)

**WildberriesAPI Class:**
- Base URL: `https://content-api.wildberries.ru`
- Endpoint: `/content/v2/get/cards/list` (cursor-based pagination)
- Key methods:
  - `fetch_all_products(with_photo=-1, limit=100, max_pages=None)` - Paginated fetch with cursor
  - `get_product_by_nmid(nm_id)` - Single product (iterates until found)
  - `get_products_by_nmids(nm_ids)` - Batch fetch (iterates until all found)

**Rate Limiting & Retries:**
- 0.12s delay between requests
- Exponential backoff for 401, 429, 5xx errors
- Max 4 retry attempts with backoff_base=0.6

### Label Generation (label_generator.py)

**Core Function: `generate_labels_sync()`**
- Creates 58x40mm product labels with DataMatrix + EAN-13 + product info
- Process flow:
  1. Takes source CIS PDF (from uploaded CISLabel)
  2. For each label (quantity):
     - Reads last page of source PDF
     - Decodes DataMatrix using pylibdmtx
     - Re-encodes DataMatrix to new label
     - Extracts GS1 text (AI codes like "(01)12345678901234")
     - Generates EAN-13 barcode (from ean_code param or extracts from GS1)
     - Renders text: title, color, size, material, country, IP name, article
     - Adds "Честный знак" logo
     - Deletes used page from source PDF
  3. Returns (output_pdf_path, updated_source_pdf_path)

**Layout:**
- DataMatrix: 23x23mm at (0.5, 15.0)
- EAN-13: Wide barcode right of DataMatrix, max width
- GS1 text: Below DataMatrix (5pt font)
- Product info: Right column (6pt font)
- Logo: Bottom left (20x6mm)

**Dependencies:**
- PyMuPDF (fitz) - PDF manipulation
- pylibdmtx - DataMatrix decode/encode
- ReportLab - PDF generation
- python-barcode - EAN-13 generation
- PIL - Image processing

**Font Handling:**
- Prefers Arial (fonts/Arial.ttf)
- Falls back to Helvetica

### Barcode Generation (barcode_generator.py)

**Core Function: `generate_delivery_barcodes()`**
- Creates 58x40mm barcode labels for WB deliveries
- Generates two PDFs:
  1. Box barcodes PDF - one Code128 barcode per box (wb_box_id)
  2. Delivery barcode PDF - single Code128 barcode (delivery_number)
- Process flow:
  1. Takes Delivery object with delivery_number, delivery_date
  2. Takes list of (DeliveryBox, items) tuples
  3. For each box: generates Code128 barcode from wb_box_id
  4. Generates single delivery barcode from delivery_number
  5. Returns (box_barcode_pdf_path, delivery_barcode_pdf_path)

**Layout:**
- Page size: 58x40mm
- Barcode size: 56x34mm (centered with margin)
- Barcode type: Code128
- Writer options: module_width=0.5, module_height=35.0, font_size=16

**Dependencies:**
- python-barcode - Code128 generation
- ReportLab - PDF generation
- PIL (ImageWriter) - Barcode rendering

### Production Workflow

**Complete workflow from products to delivery:**

1. **Setup (Products tab)**
   - Create ProductGroup with WB nmIDs
   - System fetches full product data from WB API
   - Products stored with sizes, photos, characteristics

2. **Upload CIS Labels (Labels tab)**
   - For each ProductGroup + techSize combination
   - Upload PDF containing DataMatrix codes (Честный знак)
   - Stored in database as CISLabel (binary data)

3. **Create Orders (Orders tab)**
   - Create Order from nmIDs
   - System creates one OrderItem per product size
   - User can edit: quantity, print_link, print_status, priority

4. **Print Tasks (Optional - Orders → Print Tasks)**
   - Copy selected OrderItems to PrintTasks
   - Track film_usage, print_status
   - Updates sync back to original OrderItem
   - Inventory deductions for print_film when marked complete

5. **Production Orders (Optional staging - Orders → Production Orders)**
   - Intermediate queue between Orders and Production
   - Copy selected OrderItems to ProductionOrders
   - Allows grouping and validation before final production
   - Can adjust quantities before moving to production

6. **Move to Production (Orders/Production Orders → Production)**
   - User selects OrderItems or ProductionOrders (checkbox)
   - System groups by (nm_id, tech_size)
   - For each group:
     - Looks up Product for metadata (title, color, material, country)
     - Finds corresponding CISLabel for DataMatrix source
     - Calls `generate_labels_sync()` to create labels
     - Saves generated PDF to static/labels/
     - Updates CIS source PDF (removes used pages)
     - Creates ProductionItem with labels_link
     - Deletes OrderItem or ProductionOrder (moved to production)
     - Records BrandExpense entry for tracking material usage

7. **Production Tracking (Dashboard)**
   - ProductionItems displayed with labels_link, box_number
   - User can update box assignments
   - Preserves original order (via order_item_id)

8. **Create Boxes (Production → Boxes)**
   - Select ProductionItems with box_number assigned
   - System groups by box_number
   - Creates Box records with BoxItems
   - Deducts inventory (boxes_60x40x40, bags_25x30)
   - Adds to FinishedGoodsStock
   - Deletes ProductionItems (moved to boxes)

9. **Create Deliveries (Boxes → Deliveries)**
   - Select Boxes with delivery info (delivery_number, warehouse, delivery_date)
   - System creates Delivery with DeliveryBox snapshots
   - Calls `generate_delivery_barcodes()` to create barcode PDFs
   - Stores barcode PDF paths in Delivery
   - Deletes original Box records (moved to delivery)

**Key Design Points:**
- Order items track individual sizes, not just products
- ProductionOrders provide optional staging area before production
- CIS labels are size-specific (one PDF per group+size)
- Label generation consumes source PDF pages (destructive)
- Production items are independent (order_id nullable)
- Each stage moves items forward, deleting from previous stage
- Inventory tracking integrated at box creation
- Finished goods stock updated when boxes created
- PrintTask syncs print_status back to OrderItem
- BrandExpense tracks material usage and costs per brand/date

## Code Conventions

### When Modifying Code

1. **Imports:** Keep Flask imports together, then models, then blueprints
2. **Routes:** All routes must have `@login_required` except auth and index
3. **Database Changes:** Always wrap in try/except with rollback on error
4. **Flash Messages:** Use Russian language for user-facing messages
5. **API Keys:** Never log or expose decrypted API keys

### File Organization

- **app.py** - Application initialization, main_bp routes (/, /dashboard, /settings, /select-session)
- **auth.py** - Google OAuth authentication logic
- **models.py** - Database models (User, Session, SessionMember, ProductGroup, Product, Order, OrderItem, ProductionOrder, ProductionItem, CISLabel, PrintTask, Box, BoxItem, Delivery, DeliveryBox, Inventory, FinishedGoodsStock, Defect, BrandExpense)
- **sessions_routes.py** - Session management routes (create, join, switch, leave, members)
- **session_utils.py** - Session validation helper functions (get_current_session, check_section_permission, check_modify_permission)
- **migrate_to_sessions.py** - Migration script for existing single-user data to multi-user sessions
- **wb_api.py** - Wildberries Content API v2 integration
- **products_routes.py** - Product group management routes
- **orders_routes.py** - Order creation and management routes
- **labels_routes.py** - CIS label PDF upload/download routes
- **production_orders_routes.py** - Production orders management routes (staging area before production)
- **production_routes.py** - Production workflow routes (move to production, generate labels)
- **print_tasks_routes.py** - Print task management routes
- **boxes_routes.py** - Box management routes (create boxes from production)
- **deliveries_routes.py** - Delivery management routes (create deliveries from boxes)
- **inventory_routes.py** - Inventory tracking routes
- **finished_goods_routes.py** - Finished goods stock management routes
- **defects_routes.py** - Defect tracking routes
- **brand_expenses_routes.py** - Brand expense tracking routes (material usage by brand/date)
- **label_generator.py** - Label generation logic (DataMatrix + EAN-13 + product info)
- **barcode_generator.py** - Barcode generation for deliveries (Code128)
- **config.py** - Configuration from environment variables
- **templates/select_session.html** - Session selection/creation/joining UI
- **templates/dashboard.html** - Main dashboard with session info and members display

### Common Patterns

**Creating a new route (read-only):**
```python
from session_utils import get_current_session

@products_bp.route('/endpoint', methods=['GET'])
@login_required
def handler():
    # 1. Validate active session
    session, error, code = get_current_session()
    if error:
        return error, code

    # 2. Query database with session_id filter
    items = Model.query.filter_by(session_id=session.id).all()

    # 3. Return data
    return jsonify({'items': [item.to_dict() for item in items]})
```

**Creating a new route (with modification):**
```python
from session_utils import check_section_permission

@products_bp.route('/endpoint', methods=['POST'])
@login_required
def handler():
    # 1. Validate session and check section permissions
    # Section names: 'labels', 'orders', 'production_orders', 'production', 'boxes', 'products',
    #                'deliveries', 'inventory', 'finished_goods', 'defects', 'print_tasks', 'brand_expenses'
    session, error, code = check_section_permission('orders')
    if error:
        return error, code

    # 2. Validate input
    # 3. Perform operation in try/except
    try:
        new_item = Model(
            session_id=session.id,  # For data isolation
            user_id=current_user.id,  # For audit trail
            # ... other fields
        )
        db.session.add(new_item)
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
```

**Accessing Wildberries API:**
```python
api_key = current_user.get_wb_api_key(app.config['ENCRYPTION_KEY'])
if not api_key:
    return jsonify({'error': 'API ключ не настроен'}), 400

wb_api = WildberriesAPI(api_key)
products = wb_api.get_products_by_nmids(nm_ids)
```

## Production Deployment Checklist

1. Set `SESSION_COOKIE_SECURE = True` in config.py
2. Use HTTPS with reverse proxy (Nginx/Apache)
3. Regenerate SECRET_KEY and ENCRYPTION_KEY
4. Switch to PostgreSQL/MySQL
5. Use Gunicorn/uWSGI (not Flask dev server)
6. Disable `OAUTHLIB_INSECURE_TRANSPORT`
7. Set `debug=False` in app.run()

## Known Limitations

- No test suite currently exists
- No database migration history (uses db.create_all() on startup)
- OAuth callback only configured for localhost development
- No logging configuration beyond Flask defaults
- Label generation uses temp files (not cleaned up on errors)
- CIS label consumption is destructive (pages removed from source)
- No async task queue (label generation blocks HTTP request)
- Font file (fonts/Arial.ttf) required for label generation
- Logo file required for labels (static/images/chestniy_znak.png or image.png)
- Barcode generation uses temp directory for PDF storage
- Items are deleted when moved between stages (Orders → Production → Boxes → Deliveries)
- PrintTask print_status sync with OrderItem is one-way (PrintTask → OrderItem)
- Отвечать на Русском языке