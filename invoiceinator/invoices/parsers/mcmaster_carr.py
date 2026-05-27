"""McMaster-Carr invoice parser."""

import re

from .pdf import pdf_lines
from .schema import empty_invoice, make_line_item, normalize_invoice, to_float

_VENDOR_NAME = "McMaster-Carr Supply Company"
_MONEY_RE = re.compile(r"^\$?[\d,]+\.\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_LINE_NO_RE = re.compile(r"^\d+$")
_PRODUCT_CODE_RE = re.compile(r"^(?=.*[A-Z])[A-Z0-9-]+$")


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "").strip())


def _is_money(text):
    return bool(_MONEY_RE.match(_clean(text)))


def _is_date(text):
    return bool(_DATE_RE.match(_clean(text)))


def _amount_value(text):
    m = re.search(r"[\d,]+\.\d{2}", _clean(text))
    return m.group(0).replace(",", "") if m else None


def _footer_total(lines):
    for idx in range(len(lines) - 1, -1, -1):
        if _clean(lines[idx]).upper() == "TOTAL" and idx + 1 < len(lines):
            next_line = _clean(lines[idx + 1])
            if _is_money(next_line):
                return _amount_value(next_line)
    return None


def _find_after(lines, label, predicate=None):
    for i, line in enumerate(lines):
        if _clean(line).upper() == label.upper():
            for j in range(i + 1, len(lines)):
                candidate = _clean(lines[j])
                if not candidate:
                    continue
                if predicate is None or predicate(candidate):
                    return candidate, j
            return None, None
    return None, None


def _first_match(lines, predicate):
    for i, line in enumerate(lines):
        candidate = _clean(line)
        if predicate(candidate):
            return candidate, i
    return None, None


def _header_value(lines, label):
    value, _ = _find_after(lines, label, lambda line: line and line.upper() not in {
        "BILLED TO",
        "SHIPPED TO",
        "INFORMATION ABOUT YOUR PAYMENT",
        "CREDIT CARD",
        "MERCCHANDISE",
        "MERCHANDISE",
        "SALES TAX",
        "SHIPPING",
        "TOTAL",
        "PAYMENT RECEIVED",
        "BALANCE DUE",
        "PACKING LIST",
        "ORDER CONFIRMATION",
        "PAGE 1 OF 1",
    })
    return value


def _header_date(lines):
    for label in ("INVOICE DATE", "ORDER DATE", "DATE"):
        value, _ = _find_after(lines, label, _is_date)
        if value:
            return value
    return None


def _line_item_blocks(lines):
    try:
        start = next(i for i, line in enumerate(lines) if _clean(line).upper() == "LINE")
    except StopIteration:
        return []

    blocks = []
    i = start + 1
    while i < len(lines):
        if _clean(lines[i]).upper() in {"MERCHANDISE", "PACKING LIST", "SHIPPING", "TAX"}:
            break
        if not _LINE_NO_RE.match(_clean(lines[i])):
            i += 1
            continue
        if i + 1 >= len(lines) or not _PRODUCT_CODE_RE.match(_clean(lines[i + 1])):
            i += 1
            continue

        j = i + 2
        while j < len(lines):
            if _LINE_NO_RE.match(_clean(lines[j])) and j + 1 < len(lines) and _PRODUCT_CODE_RE.match(_clean(lines[j + 1])):
                break
            if _clean(lines[j]).upper() in {"MERCHANDISE", "PACKING LIST", "SHIPPING", "TAX"}:
                break
            j += 1
        blocks.append(lines[i:j])
        i = j
    return blocks


def _parse_block(block):
    if len(block) < 6:
        return None

    product_code = _clean(block[1])
    tail = block[-3:]
    if not _is_money(tail[0]) or not _is_money(tail[2]):
        return None

    qty_idx = None
    for idx in range(2, len(block) - 3):
        line = _clean(block[idx])
        next_line = _clean(block[idx + 1]) if idx + 1 < len(block) else ""
        if _LINE_NO_RE.match(line) and next_line and not _is_money(next_line) and not _is_date(next_line):
            qty_idx = idx
            break
    if qty_idx is None:
        return None

    description_lines = [_clean(line) for line in block[2:qty_idx] if _clean(line)]
    qty = _clean(block[qty_idx])
    unit = _clean(block[qty_idx + 1]) if qty_idx + 1 < len(block) else ""
    unit_price = _amount_value(tail[0]) or "0.00"
    total_price = _amount_value(tail[2]) or "0.00"

    return make_line_item(
        item_id=product_code,
        name=" ".join(description_lines),
        description="",
        qty=qty,
        unit=unit,
        unit_price=unit_price,
        total_price=total_price,
    )


def parse_mcmaster_carr_invoice(pdf_path):
    """McMaster-Carr Supply Company receipts and order confirmations."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice(_VENDOR_NAME)

    invoice_number = None
    for label in ("INVOICE", "MCMASTER-CARR NUMBER"):
        value, idx = _find_after(lines, label, lambda line: bool(re.fullmatch(r"\d{5,}", line)))
        if value and not _is_date(value) and not _is_money(value):
            invoice_number = value
            break
    if invoice_number:
        result["invoice_number"] = invoice_number

    date_value = _header_date(lines)
    if date_value:
        result["date_ordered"] = date_value
        result["ship_date"] = date_value

    po_value = _header_value(lines, "PURCHASE ORDER")
    if po_value:
        result["cust_po"] = po_value

    total_value = _footer_total(lines)
    if total_value:
        result["invoice_total"] = total_value

    # "Paid" on receipt-style documents is the amount charged; keep it if total is missing.
    if not result["invoice_total"]:
        paid_value, _ = _find_after(lines, "PAID", _is_money)
        if paid_value:
            result["invoice_total"] = _amount_value(paid_value)

    for block in _line_item_blocks(lines):
        item = _parse_block(block)
        if item:
            result["line_items"].append(item)

    return normalize_invoice(result)


parse_mcmaster_carr_invoice.name = _VENDOR_NAME
