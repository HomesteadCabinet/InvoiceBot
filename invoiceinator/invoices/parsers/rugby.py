"""Rugby Architectural Building Products invoice parser."""

from __future__ import annotations

import re

import pymupdf as fitz

from .schema import empty_invoice, invoice_bundle, make_line_item, normalize_invoice, to_float

_VENDOR_NAME = "Rugby ABP - Salt Lake City"
_INVOICE_NUMBER_RE = re.compile(r"^\d{10}-\d{3}$")
_MONEY_RE = re.compile(r"^-?[\d,]+\.\d{2}$")
_MONEY_SLASH_RE = re.compile(r"^-?[\d,]+\.\d{2}/$")
_QTY_SLASH_RE = re.compile(r"^-?[\d,]+\.\d{4}/$")
_ITEM_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{5,}$")
_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")
_FOOTER_STOP_PHRASES = (
    "subtotal",
    "balance",
    "printed:",
    "security alert:",
    "effective january 1, 2026",
    "thank you for choosing",
    "of particular importance",
    "discoloration, normal color",
    "difference between production batches",
    "same production batch per room",
    "you can find the production number",
    "all purchasers and subsequent consumers",
    "shinnoki panels are available",
    "epa tsca",
)


def _page_lines(pdf_path, page_index):
    doc = fitz.open(pdf_path)
    try:
        if page_index >= len(doc):
            return []
        return [line.strip() for line in doc[page_index].get_text().splitlines() if line.strip()]
    finally:
        doc.close()


def _page_count(pdf_path):
    doc = fitz.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def _is_footer_line(line):
    text = (line or "").strip().lower()
    return any(text.startswith(prefix) for prefix in _FOOTER_STOP_PHRASES)


def _first_match(lines, pattern):
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(1)
    return None


def _first_value_after(lines, label):
    for i, line in enumerate(lines):
        if line == label and i + 1 < len(lines):
            return lines[i + 1].strip()
    return None


def _value_between(lines, start_label, end_label):
    start_idx = None
    for i, line in enumerate(lines):
        if line == start_label:
            start_idx = i + 1
            break
    if start_idx is None:
        return ""

    values = []
    for line in lines[start_idx:]:
        if line == end_label:
            break
        if line.endswith(":") and line not in {start_label, end_label}:
            break
        values.append(line)
    return " ".join(value for value in values if value)


def _extract_vendor_name(lines):
    for line in lines:
        if line.startswith("Rugby ABP -"):
            return line
    return _VENDOR_NAME


def _extract_invoice_number(lines):
    for line in lines:
        if _INVOICE_NUMBER_RE.match(line):
            return line
    return None


def _extract_invoice_type(lines):
    for line in lines:
        upper = line.upper()
        if upper in {"INVOICE", "CREDITMEMO", "CREDIT MEMO"}:
            return upper.replace(" ", "")
    return "INVOICE"


def _extract_invoice_total(lines):
    for label in ("Balance", "Subtotal"):
        for i, line in enumerate(lines):
            if line == label:
                for candidate in lines[i + 1 : i + 6]:
                    cleaned = candidate.replace("$", "").replace(",", "").strip()
                    if _MONEY_RE.match(cleaned):
                        return cleaned
    return None


def _extract_dates(lines):
    order_date = None
    ship_date = None
    due_date = None
    invoice_date = None

    for i, line in enumerate(lines):
        if line == "Order Date:" and i + 1 < len(lines):
            m = _DATE_RE.search(lines[i + 1])
            if m:
                order_date = m.group(0)
        elif line == "Ship Date:" and i + 1 < len(lines):
            m = _DATE_RE.search(lines[i + 1])
            if m:
                ship_date = m.group(0)
        elif line == "Invoice Date:" and i + 1 < len(lines):
            m = _DATE_RE.search(lines[i + 1])
            if m:
                invoice_date = m.group(0)

    for line in lines:
        m = re.search(r"Due Date:\s*(\d{1,2}/\d{1,2}/\d{2,4})", line, re.IGNORECASE)
        if m:
            due_date = m.group(1)
            break

    return order_date, ship_date, invoice_date, due_date


def _extract_job_value(lines):
    for i, line in enumerate(lines):
        if line != "Job:":
            continue
        values = []
        for candidate in lines[i + 1 :]:
            if candidate in {
                "Order Date:",
                "Ship Date:",
                "Sales",
                "Agents",
                "Order Type:",
                "Ordered By:",
                "Ship Via:",
                "Auth Chg:",
                "Invoice Date:",
                "Account:",
                "Branch:",
                "Phone:",
                "Fax:",
                "Delivery:",
                "Frt Term:",
                "Payment Terms:",
                "Printed:",
            }:
                break
            values.append(candidate)
        return " ".join(values).strip()
    return ""


def _is_amount_value(line):
    return bool(_MONEY_RE.match(line.replace("$", "").replace(",", "").strip()))


def _is_amount_slash_value(line):
    return bool(_MONEY_SLASH_RE.match(line.replace("$", "").replace(",", "").strip()))


def _is_qty_slash_value(line):
    return bool(_QTY_SLASH_RE.match(line.replace("$", "").replace(",", "").strip()))


def _find_item_index(lines):
    for i, line in enumerate(lines):
        if not _ITEM_ID_RE.match(line):
            continue
        if i < 2 or i + 1 >= len(lines):
            continue
        prev = lines[i - 1]
        prev2 = lines[i - 2]
        next_line = lines[i + 1]
        if _is_qty_slash_value(prev) and _is_qty_slash_value(prev2) and not _is_qty_slash_value(next_line):
            return i
    return None


def _parse_line_item(lines):
    item_index = _find_item_index(lines)
    if item_index is None:
        return None

    item_id = lines[item_index]
    unit = lines[item_index + 1] if item_index + 1 < len(lines) else "SH"
    qty_index = None
    unit_price_index = None
    for idx in range(item_index - 1, -1, -1):
        if qty_index is None and _is_qty_slash_value(lines[idx]):
            qty_index = idx
            continue
        if qty_index is not None and _is_amount_slash_value(lines[idx]):
            unit_price_index = idx
            break
    if qty_index is None or unit_price_index is None:
        return None

    qty_line = lines[qty_index]
    unit_price_line = lines[unit_price_index]
    qty = to_float(qty_line.replace("/", ""))
    unit_price = to_float(unit_price_line.replace("/", ""))

    desc_start = item_index + 2
    while desc_start < len(lines) and lines[desc_start] == unit:
        desc_start += 1
    while desc_start < len(lines) and (
        lines[desc_start] in {"SH", "ROLL"}
        or _is_qty_slash_value(lines[desc_start])
        or re.fullmatch(r"-?[\d,]+(?:\.\d+)?", lines[desc_start])
    ):
        desc_start += 1

    description_lines = []
    for line in lines[desc_start:]:
        if _is_footer_line(line):
            break
        if line in {"INVOICE", "CREDITMEMO"}:
            break
        description_lines.append(line)

    name = description_lines[0] if description_lines else item_id
    description = " ".join(description_lines[1:]) if len(description_lines) > 1 else ""

    return make_line_item(
        item_id=item_id,
        name=name,
        description=description,
        qty=str(qty).rstrip("0").rstrip(".") if qty % 1 else str(int(qty)),
        unit=unit,
        unit_price=unit_price,
        total_price=qty * unit_price,
    )


def _parse_page(lines):
    invoice_number = _extract_invoice_number(lines)
    if not invoice_number:
        return None

    invoice = empty_invoice(_extract_vendor_name(lines))
    invoice["invoice_number"] = invoice_number
    invoice_type = _extract_invoice_type(lines)
    invoice["cust_po"] = _extract_job_value(lines)
    order_date, ship_date, invoice_date, due_date = _extract_dates(lines)
    invoice["date_ordered"] = order_date or invoice_date
    invoice["ship_date"] = ship_date
    invoice["invoice_due_date"] = due_date
    invoice["invoice_total"] = _extract_invoice_total(lines)

    item = _parse_line_item(lines)
    if item:
        invoice["line_items"].append(item)

    return invoice


def parse_rugby_invoice(pdf_path):
    """Rugby ABP invoice and credit memo parser."""
    grouped = []
    current = None

    for page_index in range(_page_count(pdf_path)):
        lines = _page_lines(pdf_path, page_index)
        parsed = _parse_page(lines)
        if not parsed:
            continue
        if current and current["invoice_number"] == parsed["invoice_number"]:
            current["pages"].append(parsed)
        else:
            current = {
                "invoice_number": parsed["invoice_number"],
                "pages": [parsed],
            }
            grouped.append(current)

    invoices = []
    for group in grouped:
        merged = empty_invoice(_VENDOR_NAME)
        merged["invoice_number"] = group["invoice_number"]
        for page_invoice in group["pages"]:
            for field in ("ship_date", "date_ordered", "invoice_due_date", "cust_po", "invoice_total"):
                if not merged.get(field) and page_invoice.get(field):
                    merged[field] = page_invoice[field]
            if not merged.get("vendor_name") and page_invoice.get("vendor_name"):
                merged["vendor_name"] = page_invoice["vendor_name"]
            merged["line_items"].extend(page_invoice.get("line_items") or [])

        invoices.append(normalize_invoice(merged))

    return invoice_bundle(_VENDOR_NAME, invoices)


parse_rugby_invoice.name = _VENDOR_NAME
