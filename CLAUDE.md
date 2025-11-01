# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask web application for Wildberries (Russian marketplace) seller operations. Main features: Google OAuth authentication, encrypted API key storage, product group management, order management, CIS label generation, and production workflow tracking.

**Tech Stack:** Python 3.8+, Flask 3.0, SQLAlchemy, Flask-Login, Fernet encryption, PyMuPDF, ReportLab, pylibdmtx (DataMatrix), python-barcode (EAN-13)

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

Database is created automatically on first run via `db.create_all()` in app.py:115-116.

For migrations (if needed):
```bash
flask db init
flask db migrate -m "Migration message"
flask db upgrade
```

## Architecture

### Blueprint Structure

Ten main blueprints handle routing:

1. **auth_bp** (auth.py) - Google OAuth flow
   - `/auth/login` - Initiates OAuth
   - `/auth/callback` - Handles OAuth callback
   - `/auth/logout` - Logs out user

2. **products_bp** (products_routes.py) - Product group management
   - `/products/` - Products page
   - `/products/groups/create` - Create group with WB products
   - `/products/groups/<id>` - Get group details
   - `/products/groups/<id>/content` - Get products grouped by size
   - `/products/groups/<id>/edit` - Edit group (add/remove products)
   - `/products/groups/<id>/delete` - Delete group

3. **orders_bp** (orders_routes.py) - Order management
   - `/orders/` - List all orders
   - `/orders/<id>` - Get order with items
   - `/orders/create` - Create order from WB products (creates OrderItem per size)
   - `/orders/<id>/items/<item_id>/update` - Update order item fields
   - `/orders/<id>/delete` - Delete order

4. **labels_bp** (labels_routes.py) - CIS label PDF management
   - `/labels/` - Labels page showing groups with sizes
   - `/labels/upload` - Upload CIS label PDF for specific group+size
   - `/labels/view/<id>` - View label PDF inline
   - `/labels/download/<id>` - Download label PDF
   - `/labels/delete/<id>` - Delete label

5. **production_bp** (production_routes.py) - Production workflow
   - `/production/move-to-production` - Move selected order items to production + generate labels
   - `/production/items` - Get all production items
   - `/production/items/<id>/update` - Update production fields (labels_link, box_number, selected)
   - `/production/items/<id>/delete` - Delete production item

6. **print_tasks_bp** (print_tasks_routes.py) - Print task management
   - `/print-tasks/` - Get all print tasks
   - `/print-tasks/copy-from-order` - Copy selected order items to print tasks
   - `/print-tasks/<id>/update` - Update print task (film_usage, print_status, etc.)
   - `/print-tasks/<id>/delete` - Delete print task

7. **boxes_bp** (boxes_routes.py) - Box management
   - `/boxes/` - Get all boxes
   - `/boxes/add-from-production` - Create boxes from selected production items
   - `/boxes/<id>/update` - Update box fields (delivery info, wb_box_id, selected)
   - `/boxes/<id>/delete` - Delete box

8. **deliveries_bp** (deliveries_routes.py) - Delivery management
   - `/deliveries/` - Get all deliveries
   - `/deliveries/add-from-boxes` - Create delivery from selected boxes + generate barcodes
   - `/deliveries/<id>/update` - Update delivery status
   - `/deliveries/<id>/delete` - Delete delivery

9. **inventory_bp** (inventory_routes.py) - Inventory tracking
   - `/inventory/` - Inventory page
   - `/inventory/update` - Update inventory quantities (boxes, bags, film, paint, glue, labels)

10. **finished_goods_bp** (finished_goods_routes.py) - Finished goods stock management
    - `/finished-goods/` - Get all finished goods stocks
    - `/finished-goods/create` - Create new finished goods stock item
    - `/finished-goods/<id>/update` - Update stock quantities by size
    - `/finished-goods/<id>/delete` - Delete stock item

11. **main_bp** (app.py) - Core pages
    - `/` - Login page or redirect to dashboard
    - `/dashboard` - Main dashboard (shows all entities: groups, orders, production items, boxes, deliveries, print tasks, finished goods)
    - `/settings` - API key and business configuration (business_name, wb_api_key, ip_name)
    - `/settings/delete-api-key` - Delete WB API key
    - `/labels/<filename>` - Serve generated label PDFs

### Data Models (models.py)

**User**
- Google OAuth identity (google_id, email, name, profile_pic)
- Business settings (business_name, wb_api_key_encrypted, ip_name)
- Methods: `set_wb_api_key()`, `get_wb_api_key()`, `has_wb_api_key()`
- Relationships: One-to-many with ProductGroup, Order, ProductionItem, CISLabel (all cascade delete)

**ProductGroup**
- Links to User via user_id
- Contains multiple Product entries
- Methods: `get_products_by_size()` - groups products by techSize, `to_dict()`
- Relationships: One-to-many with Product, CISLabel (cascade delete)

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

**ProductionItem**
- Items moved from OrderItem to production
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
- Fields: product_name, color, sizes_stock_json
- Stores size quantities as JSON: {"XXS": 10, "XS": 20, "S": 30, ...}
- Methods: `get_sizes_stock()`, `set_sizes_stock()`, `get_total_quantity()`

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
- All queries filtered by current_user.id
- No raw SQL execution
- Cascade deletes prevent orphaned records

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

5. **Move to Production (Orders → Production)**
   - User selects OrderItems (checkbox)
   - System groups by (nm_id, tech_size)
   - For each group:
     - Looks up Product for metadata (title, color, material, country)
     - Finds corresponding CISLabel for DataMatrix source
     - Calls `generate_labels_sync()` to create labels
     - Saves generated PDF to static/labels/
     - Updates CIS source PDF (removes used pages)
     - Creates ProductionItem with labels_link
     - Deletes OrderItem (moved to production)

6. **Production Tracking (Dashboard)**
   - ProductionItems displayed with labels_link, box_number
   - User can update box assignments
   - Preserves original order (via order_item_id)

7. **Create Boxes (Production → Boxes)**
   - Select ProductionItems with box_number assigned
   - System groups by box_number
   - Creates Box records with BoxItems
   - Deducts inventory (boxes_60x40x40, bags_25x30)
   - Adds to FinishedGoodsStock
   - Deletes ProductionItems (moved to boxes)

8. **Create Deliveries (Boxes → Deliveries)**
   - Select Boxes with delivery info (delivery_number, warehouse, delivery_date)
   - System creates Delivery with DeliveryBox snapshots
   - Calls `generate_delivery_barcodes()` to create barcode PDFs
   - Stores barcode PDF paths in Delivery
   - Deletes original Box records (moved to delivery)

**Key Design Points:**
- Order items track individual sizes, not just products
- CIS labels are size-specific (one PDF per group+size)
- Label generation consumes source PDF pages (destructive)
- Production items are independent (order_id nullable)
- Each stage moves items forward, deleting from previous stage
- Inventory tracking integrated at box creation
- Finished goods stock updated when boxes created
- PrintTask syncs print_status back to OrderItem

## Code Conventions

### When Modifying Code

1. **Imports:** Keep Flask imports together, then models, then blueprints
2. **Routes:** All routes must have `@login_required` except auth and index
3. **Database Changes:** Always wrap in try/except with rollback on error
4. **Flash Messages:** Use Russian language for user-facing messages
5. **API Keys:** Never log or expose decrypted API keys

### File Organization

- **app.py** - Application initialization, main_bp routes (/, /dashboard, /settings)
- **auth.py** - Google OAuth authentication logic
- **models.py** - Database models (User, ProductGroup, Product, Order, OrderItem, ProductionItem, CISLabel, PrintTask, Box, BoxItem, Delivery, DeliveryBox, Inventory, FinishedGoodsStock)
- **wb_api.py** - Wildberries Content API v2 integration
- **products_routes.py** - Product group management routes
- **orders_routes.py** - Order creation and management routes
- **labels_routes.py** - CIS label PDF upload/download routes
- **production_routes.py** - Production workflow routes (move to production, generate labels)
- **print_tasks_routes.py** - Print task management routes
- **boxes_routes.py** - Box management routes (create boxes from production)
- **deliveries_routes.py** - Delivery management routes (create deliveries from boxes)
- **inventory_routes.py** - Inventory tracking routes
- **finished_goods_routes.py** - Finished goods stock management routes
- **label_generator.py** - Label generation logic (DataMatrix + EAN-13 + product info)
- **barcode_generator.py** - Barcode generation for deliveries (Code128)
- **config.py** - Configuration from environment variables

### Common Patterns

**Creating a new route:**
```python
@products_bp.route('/endpoint', methods=['GET', 'POST'])
@login_required
def handler():
    # 1. Validate input
    # 2. Query database with user_id filter
    # 3. Perform operation in try/except
    # 4. Commit or rollback
    # 5. Return JSON or redirect
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
