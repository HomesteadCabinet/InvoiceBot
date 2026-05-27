"""Yates Mouldings invoice parser."""

import re

from .pdf import pdf_lines
from .schema import empty_invoice, make_line_item, normalize_invoice

_VENDOR_NAME = "Yates Mouldings"
_SECTION_HEADERS = {"ACTIVITY", "DESCRIPTION", "QTY", "RATE", "AMOUNT"}
_STOP_LINES = {"SUBTOTAL", "TAX", "TOTAL", "BALANCE DUE"}
_QTY_RE = re.compile(r"^\d[\d,]*$")
_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_SINGLE_AMOUNT_RE = re.compile(r"^[\d,]+\.\d{2}T?$")
_RATE_AND_TOTAL_RE = re.compile(r"^([\d,]+\.\d{2})\s+([\d,]+\.\d{2})T?$")


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "").strip())


def _is_section_header(line):
    return _clean(line).upper() in _SECTION_HEADERS


def _is_stop_line(line):
    upper = _clean(line).upper()
    return upper in _STOP_LINES or upper.startswith("SUBTOTAL")


def _parse_amount_pair(line):
    cleaned = _clean(line).replace(",", "")
    m = _RATE_AND_TOTAL_RE.match(cleaned)
    if not m:
        return None
    return m.group(1), m.group(2).rstrip("T")


def _build_item_id(parts):
    parts = [_clean(part) for part in parts if _clean(part)]
    if not parts:
        return ""
    if len(parts) >= 2:
        return _clean(f"{parts[-2]} {parts[-1]}")
    return parts[-1]


def _next_match(lines, start, predicate):
    for i in range(start, len(lines)):
        line = _clean(lines[i])
        if predicate(line):
            return line, i
    return None, None


def parse_yates_mouldings_invoice(pdf_path):
    """Yates Mouldings invoices with repeated description/activity/size rows."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice(_VENDOR_NAME)

    try:
        header_start = next(i for i, line in enumerate(lines) if _clean(line).upper() == "INVOICE #")
    except StopIteration:
        header_start = None

    if header_start is not None:
        invoice_number, idx = _next_match(lines, header_start + 1, lambda line: bool(re.fullmatch(r"\d+", line)))
        if invoice_number:
            result["invoice_number"] = invoice_number

        date_value, idx = _next_match(lines, (idx or header_start) + 1, lambda line: bool(_DATE_RE.match(line)))
        if date_value:
            result["date_ordered"] = date_value
            result["ship_date"] = date_value

        total_value, idx = _next_match(
            lines,
            (idx or header_start) + 1,
            lambda line: bool(re.search(r"[\d,]+\.\d{2}", line)),
        )
        if total_value:
            m = re.search(r"[\d,]+\.\d{2}", total_value)
            if m:
                result["invoice_total"] = m.group(0).replace(",", "")

        due_value, _ = _next_match(lines, (idx or header_start) + 1, lambda line: bool(_DATE_RE.match(line)))
        if due_value:
            result["invoice_due_date"] = due_value

        po_value = None
        try:
            po_start = next(i for i, line in enumerate(lines) if _clean(line).upper() == "P.O. NUMBER")
        except StopIteration:
            po_start = None
        if po_start is not None:
            for line in lines[po_start + 1 :]:
                cleaned = _clean(line)
                upper = cleaned.upper()
                if upper == "DATE":
                    break
                if upper == "SHOP":
                    continue
                if cleaned:
                    po_value = cleaned
                    break
        if po_value and po_value.upper() not in {"SHOP", "DATE"}:
            result["cust_po"] = po_value

    try:
        start = next(i for i, line in enumerate(lines) if _clean(line).upper() == "AMOUNT") + 1
    except StopIteration:
        return normalize_invoice(result)

    buffer = []
    i = start
    while i < len(lines):
        line = _clean(lines[i])

        if _is_stop_line(line):
            break
        if not line or line in {"P.O. NUMBER", "SHOP", "DATE"} or _is_section_header(line):
            i += 1
            continue

        if _QTY_RE.match(line) and buffer:
            qty = line.replace(",", "")
            i += 1
            if i >= len(lines):
                break

            rate = total = None
            next_line = _clean(lines[i])
            pair = _parse_amount_pair(next_line)
            if pair:
                rate, total = pair
                i += 1
            else:
                if _SINGLE_AMOUNT_RE.match(next_line.replace(",", "")):
                    rate = next_line.rstrip("T").replace(",", "")
                    i += 1
                if i < len(lines):
                    total_line = _clean(lines[i]).replace(",", "").rstrip("T")
                    if _SINGLE_AMOUNT_RE.match(total_line):
                        total = total_line
                        i += 1

            description_lines = buffer[:]
            name = description_lines[0] if description_lines else ""
            description = " ".join(description_lines[1:]) if len(description_lines) > 1 else ""
            result["line_items"].append(
                make_line_item(
                    item_id=_build_item_id(description_lines),
                    name=name,
                    description=description,
                    qty=qty,
                    unit_price=rate or 0.0,
                    total_price=total or 0.0,
                )
            )
            buffer = []
            continue

        buffer.append(line)
        i += 1

    return normalize_invoice(result)


parse_yates_mouldings_invoice.name = _VENDOR_NAME
