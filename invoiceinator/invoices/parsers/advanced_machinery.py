"""Advanced Machinery invoice and customer statement parser."""

import re

from .pdf import pdf_lines, value_after
from .schema import (
    empty_invoice,
    invoice_bundle,
    make_line_item,
    normalize_invoice,
    to_float,
)

_VENDOR = "Advanced Machinery"

_LINE_NO_RE = re.compile(r"^\d+$")
_QTY_UOM_RE = re.compile(r"^(\d+\.\d{2})(?:\s+(\w+))?$")
_AMOUNT_RE = re.compile(r"^-?[\d,]+\.\d{2}$")

_UNIT_MAP = {
    "EA": "Each",
}

_STATEMENT_ROW_LEN = 8


def _is_statement(lines):
    return bool(lines) and lines[0] == "Customer Statement"


def _format_qty(qty_str):
    qty_f = to_float(qty_str)
    if qty_f == int(qty_f):
        return str(int(qty_f))
    return str(qty_str)


def _split_item_description(text):
    if ":" not in text:
        return "", text.strip()
    prefix, rest = text.split(":", 1)
    prefix = prefix.strip()
    rest = rest.strip()
    if prefix and len(prefix) <= 40:
        return prefix, rest
    return "", text.strip()


def _parse_invoice_header(lines, result):
    ref = value_after(lines, "Reference No.:")
    if ref:
        result["invoice_number"] = ref.strip()

    invoice_date = value_after(lines, "Date:")
    if invoice_date:
        result["date_ordered"] = invoice_date
        result["ship_date"] = invoice_date

    due_date = value_after(lines, "Due Date:")
    if due_date:
        result["invoice_due_date"] = due_date

    for i, line in enumerate(lines):
        if line == "Customer PO:" and i + 1 < len(lines):
            po = lines[i + 1].strip()
            if po and not po.endswith(":"):
                result["cust_po"] = po
            break

    for i, line in enumerate(lines):
        if line == "Total (USD):" and i + 1 < len(lines):
            cleaned = lines[i + 1].replace(",", "").strip()
            if _AMOUNT_RE.match(cleaned.replace(",", "")):
                result["invoice_total"] = cleaned.replace(",", "")
            break


def _line_items_start(lines):
    for i, line in enumerate(lines):
        if line == "EXTENDED PRICE":
            return i + 1
    return None


def _parse_invoice_line_items(lines):
    start = _line_items_start(lines)
    if start is None:
        return []

    items = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line in ("Sales Total:", "Tax Total:", "Total (USD):", "Page:"):
            break
        if not _LINE_NO_RE.match(line):
            i += 1
            continue

        i += 1
        desc_parts = []
        while i < len(lines):
            if _QTY_UOM_RE.match(lines[i]):
                break
            if _LINE_NO_RE.match(lines[i]) and desc_parts:
                break
            if lines[i] in ("Sales Total:", "Tax Total:", "Total (USD):"):
                break
            desc_parts.append(lines[i])
            i += 1

        if i >= len(lines) or not _QTY_UOM_RE.match(lines[i]):
            break

        qty_match = _QTY_UOM_RE.match(lines[i])
        qty = _format_qty(qty_match.group(1))
        unit_code = (qty_match.group(2) or "EA").upper()
        i += 1

        if i >= len(lines) or not _AMOUNT_RE.match(lines[i]):
            break
        unit_price = to_float(lines[i])
        i += 1

        if i >= len(lines) or not _AMOUNT_RE.match(lines[i]):
            break
        total_price = to_float(lines[i])
        i += 1

        full_desc = " ".join(desc_parts).strip()
        item_id, name = _split_item_description(full_desc)
        if not name:
            name = full_desc
        if not item_id and full_desc.lower().startswith("freight"):
            item_id = "Freight"

        items.append(
            make_line_item(
                item_id=item_id,
                name=name,
                description=full_desc if name != full_desc else "",
                qty=qty,
                unit=_UNIT_MAP.get(unit_code, unit_code),
                unit_price=unit_price,
                total_price=total_price,
            )
        )

    return items


def _parse_statement(lines):
    start = None
    for i, line in enumerate(lines):
        if line == "Balance":
            start = i + 1
            break
    if start is None:
        return []

    invoices = []
    i = start
    while i + _STATEMENT_ROW_LEN <= len(lines):
        row = lines[i : i + _STATEMENT_ROW_LEN]
        if not _AMOUNT_RE.match(row[5].replace(",", "")):
            break

        inv = empty_invoice(_VENDOR)
        inv["date_ordered"] = row[0]
        inv["invoice_due_date"] = row[1]
        inv["ship_date"] = row[0]
        inv["invoice_number"] = row[3]
        inv["cust_po"] = row[4]
        inv["invoice_total"] = row[5].replace(",", "")
        invoices.append(normalize_invoice(inv))
        i += _STATEMENT_ROW_LEN

    return invoices


def parse_advanced_machinery_invoice(pdf_path):
    """
    Advanced Machinery — product invoices and customer statements.

    Invoices use Reference No., line items (NO / ITEM / QTY. UOM / prices).
    Statements list open invoices (Date, Due Date, Ref. Nbr., Ext. Ref., Amount).
    """
    lines = pdf_lines(pdf_path)
    if _is_statement(lines):
        return invoice_bundle(_VENDOR, _parse_statement(lines))

    result = empty_invoice(_VENDOR)
    _parse_invoice_header(lines, result)
    result["line_items"] = _parse_invoice_line_items(lines)
    return normalize_invoice(result)


parse_advanced_machinery_invoice.name = "Advanced Machinery"
