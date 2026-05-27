"""Sherwin-Williams invoice parser."""

from __future__ import annotations

import re

import pymupdf as fitz

from .schema import empty_invoice, make_line_item, normalize_invoice

_VENDOR_NAME = "The Sherwin-Williams Co."
_MONTH_MAP = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}
_INVOICE_NO_RE = re.compile(r"^No\.\s*(.+)$", re.IGNORECASE)
_DUE_RE = re.compile(r"TERMS:\s*NET PAYMENT DUE ON\s+([A-Z]{3,4})\.?\s*(\d{1,2})(?:st|nd|rd|th)", re.IGNORECASE)
_TOTAL_RE = re.compile(r"^\$?([\d,]+\.\d{2})$")
_DISCOUNT_RE = re.compile(r"^DISCOUNT\s+\(%\s+[\d.]+\)\s+(-?[\d,]+\.\d{2})$", re.IGNORECASE)


def _pages(pdf_path):
    doc = fitz.open(pdf_path)
    try:
        return [
            [line.strip() for line in page.get_text().splitlines() if line.strip()]
            for page in doc
        ]
    finally:
        doc.close()


def _page_rows(page, y_min=280, y_max=360):
    rows = {}
    for x0, y0, x1, y1, text, block, line, word in page.get_text("words"):
        if not text or text == "-" or set(text) == {"-"}:
            continue
        if y0 < y_min or y0 > y_max:
            continue
        rows.setdefault(round(y0, 1), []).append((x0, text))
    return [" ".join(text for _, text in sorted(rows[y])) for y in sorted(rows)]


def _extract_invoice_number(lines):
    for idx, line in enumerate(lines):
        if line.upper() == "INVOICE" and idx + 1 < len(lines):
            m = _INVOICE_NO_RE.match(lines[idx + 1])
            if m:
                return m.group(1)
        m = _INVOICE_NO_RE.match(line)
        if m:
            return m.group(1)
    return None


def _extract_due_date(lines):
    for line in lines:
        m = _DUE_RE.search(line)
        if m:
            month = _MONTH_MAP.get(m.group(1)[:3].upper(), "01")
            day = f"{int(m.group(2)):02d}"
            return f"{month}/{day}/26"
    return None


def _extract_charge(lines):
    for idx, line in enumerate(lines):
        if line.upper() == "CHARGE" and idx + 1 < len(lines):
            m = _TOTAL_RE.match(lines[idx + 1].replace("$", ""))
            if m:
                return m.group(1)
    for line in reversed(lines):
        if line.startswith("CHARGE $"):
            return line.split("$", 1)[1].strip()
    return None


def _extract_subtotal(lines):
    for idx, line in enumerate(lines):
        if line.upper() == "SUBTOTAL BEFORE TAX" and idx + 1 < len(lines):
            m = _TOTAL_RE.match(lines[idx + 1])
            if m:
                return m.group(1)
    return None


def _extract_sales_tax(lines):
    for idx, line in enumerate(lines):
        if "SALES TAX" in line.upper() and idx + 1 < len(lines):
            m = _TOTAL_RE.match(lines[idx + 1])
            if m:
                return m.group(1)
    return None


def _extract_account(lines):
    for line in lines:
        if line.startswith("ACCOUNT:"):
            return line.split("ACCOUNT:", 1)[1].strip()
    return None


def _extract_item_lines(page):
    items = []
    for line in _page_rows(page):
        if not line:
            continue
        if line.upper().startswith("DISCOUNT"):
            m = _DISCOUNT_RE.match(line)
            if m:
                amount = float(m.group(1).replace(",", ""))
                items.append(
                    make_line_item(
                        item_id="DISCOUNT",
                        name="Discount",
                        description="Sherwin-Williams discount",
                        qty="1",
                        unit="EA",
                        unit_price=amount,
                        total_price=amount,
                    )
                )
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        if re.fullmatch(r"[A-Z0-9-]+", parts[0]) and re.fullmatch(r"\d+", parts[-3]) and re.fullmatch(r"[\d,]+\.\d{2}", parts[-2]) and re.fullmatch(r"[\d,]+\.\d{2}", parts[-1]):
            item_id = parts[0]
            unit = parts[1]
            qty = parts[-3]
            unit_price = float(parts[-2].replace(",", ""))
            total_price = float(parts[-1].replace(",", ""))
            name = " ".join(parts[2:-3]).strip()
            items.append(
                make_line_item(
                    item_id=item_id,
                    name=name or item_id,
                    description=unit,
                    qty=qty,
                    unit=unit,
                    unit_price=unit_price,
                    total_price=total_price,
                )
            )
    return items


def parse_sherwin_invoice(pdf_path):
    """Sherwin-Williams invoice parser."""
    doc = fitz.open(pdf_path)
    try:
        pages = [
            [line.strip() for line in page.get_text().splitlines() if line.strip()]
            for page in doc
        ]
        lines = [line for page in pages for line in page]
        page = doc[0]

        invoice = empty_invoice(_VENDOR_NAME)
        invoice_number = _extract_invoice_number(lines)
        invoice["invoice_number"] = invoice_number
        invoice["invoice_due_date"] = _extract_due_date(lines)
        invoice["date_ordered"] = invoice["invoice_due_date"]
        invoice["ship_date"] = invoice["invoice_due_date"]
        invoice["cust_po"] = _extract_account(lines) or invoice_number
        invoice["invoice_total"] = _extract_charge(lines)
        invoice["line_items"] = _extract_item_lines(page)

        subtotal = _extract_subtotal(lines)
        if subtotal and not invoice["invoice_total"]:
            invoice["invoice_total"] = subtotal

        return normalize_invoice(invoice)
    finally:
        doc.close()


parse_sherwin_invoice.name = _VENDOR_NAME
