# label_generator.py

import io
import os
import re
import tempfile
from datetime import datetime

import fitz  # PyMuPDF
from PIL import Image
from pylibdmtx.pylibdmtx import decode, encode
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit

# EAN13
from io import BytesIO
from barcode import get_barcode_class
from barcode.writer import ImageWriter

# --- шрифт ---
try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    FONT_NAME = "Arial"
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Arial", "fonts/Arial.ttf"))
except Exception:
    FONT_NAME = "Helvetica"


# ------------------ EAN из входа (как в боте) ------------------
def _make_ean_reader(ean_code: str) -> ImageReader | None:
    """
    Возвращает ImageReader для EAN-13, не создавая файлов на диске.
    Поддерживает вход длиной 12 или 13 цифр (для 12 контрольная посчитается автоматически).
    """
    if not ean_code:
        return None
    code = ean_code.strip()
    if not (code.isdigit() and len(code) in (12, 13)):
        return None
    try:
        ean_cls = get_barcode_class("ean13")  # для 12 цифр сама досчитает контрольную
        ean_obj = ean_cls(code, writer=ImageWriter())
        buf = BytesIO()
        ean_obj.write(buf)  # опции по умолчанию — как в боте
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


# ------------------ Фолбэк: EAN из GS1 (01 + GTIN-14) ------------------
def _ean13_from_gs1(gs1_text: str | None) -> str | None:
    """
    Достаём GTIN-14 из GS1 (AI (01)) и конвертируем в EAN-13,
    если первый символ GTIN-14 == '0'.
    Поддерживает '(01)12345678901234', '01 12345678901234', '01XXXXXXXXXXXXXX'.
    """
    if not gs1_text:
        return None
    s = re.sub(r"\s+", "", gs1_text)
    m = re.search(r"\(01\)(\d{14})", s) or re.search(r"01(\d{14})", s)
    if not m:
        return None
    g14 = m.group(1)
    if g14[0] != "0":
        return None
    d13 = g14[1:]  # убрали ведущий 0

    def checksum_ean13(d12: str) -> int:
        total = 0
        for i, ch in enumerate(d12):
            d = int(ch)
            total += d if i % 2 == 0 else 3 * d
        return (10 - (total % 10)) % 10

    return d13[:-1] + str(checksum_ean13(d13[:-1]))


# ------------------ Основной генератор ------------------
def generate_labels_sync(
    local_pdf_path: str,
    quantity: int,
    title: str,
    color: str,
    wb_size: str,
    material: str,
    ean_code: str,  # сначала пробуем его (12/13), если нет — фолбэк из GS1
    country: str,
    ip_name: str,
    nm_id: int | str,
):
    """
    - Последняя страница → decode DM → encode → рисуем
    - EAN: ean_code (12/13) или фолбэк из GS1 (01+GTIN-14 → EAN-13)
    - Порядок ОТРИСОВКИ: сперва DM, потом EAN
    - EAN ставим СРАЗУ ПРАВЕЕ DM и делаем ШИРЕ (на всю правую колонку)
    - Страница 58×40 мм
    """
    if not os.path.exists(local_pdf_path):
        raise FileNotFoundError(f"Исходный PDF не найден: {local_pdf_path}")

    doc = fitz.open(local_pdf_path)

    tmp_dir = tempfile.gettempdir()
    base_name = os.path.basename(local_pdf_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(tmp_dir, f"labels_{stamp}_{base_name}.pdf")
    updated_path = os.path.join(tmp_dir, f"updated_{stamp}_{base_name}")

    # страница как в боте
    PAGE_W_MM, PAGE_H_MM = 58.0, 40.0
    c = canvas.Canvas(output_path, pagesize=(PAGE_W_MM * mm, PAGE_H_MM * mm))

    # блок DM (как в боте)
    DM_X_MM, DM_Y_MM, DM_W_MM, DM_H_MM = 0.5, 15.0, 23.0, 23.0

    # EAN: хотим «шире и чуть правее» → сразу за DM
    # чуть меньше зазор/правое поле → больше ширина в правой колонке
    GAP_MM = 0.5
    RIGHT_MARGIN_MM = 0.25

    EAN_X_MM = DM_X_MM + DM_W_MM + GAP_MM
    EAN_Y_MM = 0.0
    EAN_W_MM = max(37.0, PAGE_W_MM - EAN_X_MM - RIGHT_MARGIN_MM)  # вся доступная ширина справа
    EAN_H_MM = 18.0  # высота как в боте

    # заранее подготовим EAN из входного кода (как в боте)
    ean_reader_global = _make_ean_reader(ean_code)

    qty = max(0, int(quantity))
    for _ in range(qty):
        if doc.page_count == 0:
            break

        page = doc[-1]

        # --- 1) DM: decode исходника ---
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        try:
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            decoded = decode(img)
        finally:
            try:
                img.close()
            except Exception:
                pass
            del pix

        # GS1-строка (AI 01…)
        try:
            text = page.get_text("text") or ""
        except Exception:
            text = ""
        gs1_code = next(
            (ln.strip() for ln in text.splitlines() if ln.strip().startswith(("01", "(01)"))),
            ""
        )

        # --- 2) СНАЧАЛА РИСУЕМ DM ---
        code_raw = None
        if decoded:
            try:
                code_raw = decoded[0].data.decode("utf-8").replace("|", "\x1d")
            except Exception:
                code_raw = None

        if code_raw:
            try:
                enc = encode(code_raw.encode("utf-8"))
                dmtx_img = Image.frombytes('RGB', (enc.width, enc.height), enc.pixels)
                b = io.BytesIO()
                dmtx_img.save(b, format='PNG')
                b.seek(0)
                c.drawImage(ImageReader(b), DM_X_MM * mm, DM_Y_MM * mm, width=DM_W_MM * mm, height=DM_H_MM * mm)
            except Exception:
                pass

        # --- 3) ПОТОМ РИСУЕМ EAN (правее и шире) ---
        ean_reader = ean_reader_global
        if ean_reader is None:
            ean_from_gs1 = _ean13_from_gs1(gs1_code)
            if ean_from_gs1:
                ean_reader = _make_ean_reader(ean_from_gs1)

        if ean_reader:
            # КЛЮЧЕВАЯ ПРАВКА: НЕ передаём height → масштаб по ширине
            c.drawImage(
                ean_reader,
                EAN_X_MM * mm, EAN_Y_MM * mm,
                width=EAN_W_MM * mm,
                preserveAspectRatio=True,
                anchor='sw'
            )

        # --- 4) GS1-строка текстом (под DM) ---
        c.setFont(FONT_NAME, 5)
        if gs1_code:
            if len(gs1_code) > 21:
                c.drawString(1 * mm, 12 * mm, gs1_code[:21])
                c.drawString(1 * mm, 10 * mm, gs1_code[21:])
            else:
                c.drawString(1 * mm, 12 * mm, gs1_code)

        # --- 5) Тексты справа ---
        c.setFont(FONT_NAME, 6)
        text_x = 25 * mm
        text_y = 37 * mm
        for line in simpleSplit(title or "", FONT_NAME, 6, 30 * mm):
            c.drawString(text_x, text_y, line)
            text_y -= 2.5 * mm
        if color:
            c.drawString(text_x, text_y, f"Цвет: {color}");    text_y -= 2.5 * mm
        if wb_size:
            c.drawString(text_x, text_y, f"Размер: {wb_size}"); text_y -= 2.5 * mm
        if material:
            c.drawString(text_x, text_y, f"Состав: {material}"); text_y -= 2.5 * mm
        if country:
            c.drawString(text_x, text_y, f"Страна: {country}");  text_y -= 2.5 * mm
        if ip_name:
            c.drawString(text_x, text_y, f"ИП: {ip_name}")
        c.drawString(text_x, max(2.5 * mm, text_y - 2.5 * mm), f"Арт. {nm_id}")

        # --- 6) Лого слева внизу ---
        logo_paths = [
            "static/images/chestniy_znak.png",
            "static/images/image.png",
            "images.png",
            "image.png"
        ]
        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                c.drawImage(logo_path, 2 * mm, 3 * mm, width=20 * mm, height=6 * mm)
                break

        c.showPage()
        doc.delete_page(-1)

    c.save()
    doc.save(updated_path, incremental=False, garbage=4)
    doc.close()

    return output_path, updated_path
