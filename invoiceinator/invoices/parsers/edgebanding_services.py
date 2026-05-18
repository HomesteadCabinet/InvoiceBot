"""Edgebanding Services Inc invoice parser (ESI / eb*.pdf)."""

import re

import pymupdf as fitz

from .pdf import pdf_lines, pdf_text
from .schema import empty_invoice, make_line_item, normalize_invoice, to_float

_VENDOR = "Edgebanding Services"
_INVOICE_RE = re.compile(r"\b(\d{10}-\d{3})\b")
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2,4}$")
# Edgebanding (P…) and hot-melt / supply (JW…) product codes
_ITEM_CODE_RE = re.compile(r"^(?:P\d*|JW)-[\w-]+$", re.I)
_PRICE_SLASH_RE = re.compile(r"^([\d.]+)/\s*$")
_AMOUNT_RE = re.compile(r"^[\d,]+\.\d{2}$")

_TABLE_Y_MIN = 300
_TABLE_Y_MAX = 405
_ROW_Y_TOLERANCE = 3
_ITEM_X_MIN = 160
_DESC_X_MIN = 160
_DESC_X_MAX = 370
_QTY_X_MAX = 135
_UOM_X_MAX = 160
_AMOUNT_X_MIN = 520
_PRICE_X_MIN = 440
_PRICE_X_MAX = 520


def _eb_spans(pdf_path):
    page = fitz.open(pdf_path)[0]
    spans = []
    for block in page.get_text("dict")["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            bbox = line["bbox"]
            spans.append({"y": bbox[1], "x": bbox[0], "text": text})
    return spans


def _eb_cust_po(lines):
    for index, line in enumerate(lines):
        if line != "Job:":
            continue
        candidates = []
        for value in lines[index + 1 : index + 5]:
            value = value.strip()
            if not value or value in ("PO:", "Ref:", "Order Date:", "Ship Date:"):
                continue
            if _DATE_RE.match(value) or value in ("Sales", "Agents"):
                break
            candidates.append(value)
        if len(candidates) >= 2:
            number_match = re.match(r"^(\d+)\s*", candidates[0])
            last = candidates[-1]
            if number_match and not last.startswith(number_match.group(1)):
                return f"{number_match.group(1)} {last}".strip()
            return last
        if candidates:
            return candidates[-1]
    return None


def _eb_order_and_ship_dates(lines):
    for index, line in enumerate(lines):
        if line != "Order Date:":
            continue
        dates = []
        for value in lines[index + 1 : index + 6]:
            if _DATE_RE.match(value):
                dates.append(value)
        if dates:
            return dates[0], dates[-1]
    return None, None


def _eb_invoice_number(lines, text):
    """Prefer invoice # on the account line above Frt Term (avoids header typos)."""
    for index, line in enumerate(lines):
        if not line.startswith("Frt Term:"):
            continue
        for prior in range(index - 1, max(0, index - 8), -1):
            match = _INVOICE_RE.search(lines[prior])
            if match:
                return match.group(1)
    matches = _INVOICE_RE.findall(text)
    return matches[-1] if matches else None


def _eb_fill_metadata(result, lines, text):
    invoice_number = _eb_invoice_number(lines, text)
    if invoice_number:
        result["invoice_number"] = invoice_number

    due_match = re.search(r"Due Date:\s*(\d{2}/\d{2}/\d{2,4})", text)
    if due_match:
        result["invoice_due_date"] = due_match.group(1)

    cust_po = _eb_cust_po(lines)
    if cust_po:
        result["cust_po"] = cust_po

    ordered, shipped = _eb_order_and_ship_dates(lines)
    if ordered:
        result["date_ordered"] = ordered
    if shipped:
        result["ship_date"] = shipped

    for pattern in (
        r"Balance\s*\n\s*\$?([\d,]+\.\d{2})",
        r"Subtotal\s*\n\s*([\d,]+\.\d{2})",
    ):
        total_match = re.search(pattern, text)
        if total_match:
            result["invoice_total"] = total_match.group(1).replace(",", "")
            break


def _eb_row_spans(table_spans, row_y):
    return [span for span in table_spans if abs(span["y"] - row_y) <= _ROW_Y_TOLERANCE]


def _eb_description_lines(table_spans, row_y, next_row_y):
    upper = next_row_y if next_row_y is not None else _TABLE_Y_MAX
    desc = [
        span
        for span in table_spans
        if row_y + 5 < span["y"] < upper - 3
        and _DESC_X_MIN <= span["x"] <= _DESC_X_MAX
        and not _ITEM_CODE_RE.match(span["text"])
        and span["text"] != "Subtotal"
    ]
    desc.sort(key=lambda span: span["y"])
    return [span["text"] for span in desc]


def _eb_parse_line_items(spans):
    table_spans = [
        span for span in spans if _TABLE_Y_MIN < span["y"] < _TABLE_Y_MAX
    ]
    item_rows = sorted(
        (
            span
            for span in table_spans
            if _ITEM_CODE_RE.match(span["text"]) and span["x"] >= _ITEM_X_MIN
        ),
        key=lambda span: span["y"],
    )

    items = []
    for index, item_span in enumerate(item_rows):
        row_y = item_span["y"]
        next_row_y = (
            item_rows[index + 1]["y"] if index + 1 < len(item_rows) else None
        )
        row = _eb_row_spans(table_spans, row_y)

        qty_values = []
        unit = "LF"
        unit_price = 0.0
        total_price = 0.0
        for span in row:
            text = span["text"]
            if span["x"] < _QTY_X_MAX and text.isdigit():
                qty_values.append(text)
            elif span["x"] < _UOM_X_MAX and text.isalpha() and len(text) <= 4:
                unit = text
            elif _PRICE_X_MIN <= span["x"] <= _PRICE_X_MAX:
                price_match = _PRICE_SLASH_RE.match(text)
                if price_match:
                    unit_price = to_float(price_match.group(1))
            elif span["x"] >= _AMOUNT_X_MIN and _AMOUNT_RE.match(text):
                total_price = to_float(text)

        qty = qty_values[-1] if qty_values else "1"
        desc_lines = _eb_description_lines(table_spans, row_y, next_row_y)
        name = desc_lines[0] if desc_lines else item_span["text"]
        description = " ".join(desc_lines) if desc_lines else name

        items.append(
            make_line_item(
                item_id=item_span["text"],
                name=name,
                description=description,
                qty=qty,
                unit=unit,
                unit_price=unit_price,
                total_price=total_price or (unit_price * to_float(qty)),
            )
        )
    return items


def parse_edgebanding_services_invoice(pdf_path):
    """Edgebanding Services Inc (ESI-Utah) invoices with multi-line descriptions."""
    lines = pdf_lines(pdf_path)
    text = pdf_text(pdf_path)
    result = empty_invoice(_VENDOR)
    _eb_fill_metadata(result, lines, text)
    result["line_items"] = _eb_parse_line_items(_eb_spans(pdf_path))
    return normalize_invoice(result)


parse_edgebanding_services_invoice.name = "Edgebanding Services"
