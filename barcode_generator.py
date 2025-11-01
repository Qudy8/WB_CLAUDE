# barcode_generator.py

import os
import re
import tempfile
from datetime import datetime
from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from barcode import get_barcode_class
from barcode.writer import ImageWriter


def generate_delivery_barcodes(delivery, boxes_with_items):
    """
    Generate barcode PDFs for delivery and boxes.

    Args:
        delivery: Delivery object with delivery_number, delivery_date
        boxes_with_items: List of tuples [(box, items), ...]
            box: DeliveryBox object with box_number, wb_box_id
            items: List of items in the box (each with quantity field)

    Returns:
        tuple: (box_barcode_pdf_path, delivery_barcode_pdf_path)
    """

    # Clean delivery number for barcode
    delivery_number = str(delivery.delivery_number or '').strip()
    safe_num = re.sub(r"[^\w\-]", "-", delivery_number)
    safe_num = re.sub(r"-+", "-", safe_num).strip("-")

    if not safe_num:
        raise ValueError("Номер поставки не может быть пустым")

    # Clean date for filename
    try:
        parsed = datetime.fromisoformat(str(delivery.delivery_date).replace("Z", "").replace("T", " "))
        safe_date = parsed.strftime("%Y-%m-%d")
    except Exception:
        raw_date = str(delivery.delivery_date or '').strip()
        safe_date = re.sub(r"[^\w\-]", "-", raw_date)
        safe_date = re.sub(r"-+", "-", safe_date).strip("-")

    # Create temp directory
    tmp_dir = tempfile.gettempdir()

    # Page size: 58x40mm
    page_w, page_h = 58 * mm, 40 * mm
    barcode_w, barcode_h = 56 * mm, 34 * mm
    margin_y = (page_h - barcode_h) / 2

    # Barcode generation options
    writer_options = {
        "module_width": 0.5,
        "module_height": 35.0,
        "font_size": 16,
        "text_distance": 7.0,
        "quiet_zone": 2.0
    }

    # ===============================
    # 1. Generate Box Barcodes PDF
    # ===============================
    pdf_boxes_name = f"wb_boxes_{safe_date}_{safe_num}.pdf"
    pdf_boxes_path = os.path.join(tmp_dir, pdf_boxes_name)

    c = canvas.Canvas(pdf_boxes_path, pagesize=(page_w, page_h))

    for box, items in boxes_with_items:
        # Get wb_box_id for barcode
        wb_box_id = str(box.wb_box_id or '').strip()
        if not wb_box_id:
            continue  # Skip boxes without WB box ID

        # Generate barcode for this box (one barcode per box)
        code128 = get_barcode_class('code128')
        barcode_obj = code128(wb_box_id, writer=ImageWriter())

        # Save to BytesIO instead of file
        buffer = BytesIO()
        barcode_obj.write(buffer, writer_options)
        buffer.seek(0)

        # Draw barcode on PDF
        x = (page_w - barcode_w) / 2
        img_reader = ImageReader(buffer)
        c.drawImage(img_reader, x, margin_y, width=barcode_w, height=barcode_h,
                   preserveAspectRatio=True, anchor='c')

        c.showPage()

    c.save()

    # ===============================
    # 2. Generate Delivery Barcode PDF
    # ===============================
    pdf_supply_name = f"wb_supply_{safe_date}_{safe_num}.pdf"
    pdf_supply_path = os.path.join(tmp_dir, pdf_supply_name)

    c = canvas.Canvas(pdf_supply_path, pagesize=(page_w, page_h))

    # Repeat delivery barcode (number of boxes + 1)
    num_pages = len(boxes_with_items) + 1

    for _ in range(num_pages):
        code128 = get_barcode_class('code128')
        barcode_obj = code128(safe_num, writer=ImageWriter())

        # Save to BytesIO
        buffer = BytesIO()
        barcode_obj.write(buffer, writer_options)
        buffer.seek(0)

        # Draw barcode on PDF
        x = (page_w - barcode_w) / 2
        img_reader = ImageReader(buffer)
        c.drawImage(img_reader, x, margin_y, width=barcode_w, height=barcode_h,
                   preserveAspectRatio=True, anchor='c')

        c.showPage()

    c.save()

    return pdf_boxes_path, pdf_supply_path
