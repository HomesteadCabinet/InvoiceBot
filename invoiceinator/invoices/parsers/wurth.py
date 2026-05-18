"""Wurth Louis and Company invoice parser."""

import re

import pymupdf as fitz

from .schema import (
    empty_invoice,
    invoice_bundle,
    make_line_item,
    normalize_invoice,
    to_float,
)

_WURTH_VENDOR = "Wurth Louis and Company"
_WURTH_COLUMN_HEADERS = frozenset({
    "QTY ORD",
    "QTY SHIP",
    "PART NUMBER",
    "DESCRIPTION",
    "UNIT PRICE",
    "U/M",
    "TAX",
    "AMOUNT",
    "SUBTOTAL",
    "ENERGY FEE",
    "TOTAL AMOUNT",
})
_PART_NUMBER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-/()]*$", re.I)
_AMOUNT_RE = re.compile(r"^\(?\$?[\d,]+\.\d{2}\)?$")
_DISCLAIMER_PHRASES = (
    "FOR INDUSTRIAL",
    "RESALE OR CONSUMER",
    "NOT FOR RESALE",
)


def _wurth_page_lines(pdf_path, page_index=0):
    doc = fitz.open(pdf_path)
    if page_index >= len(doc):
        return []
    return [line.strip() for line in doc[page_index].get_text().splitlines() if line.strip()]


def _wurth_page_count(pdf_path):
    doc = fitz.open(pdf_path)
    return len(doc)


def _wurth_page_is_invoice(lines):
    """True when a PDF page contains a Wurth invoice or credit memo."""
    if not lines:
        return False
    if "INVOICE #" in lines:
        return True
    header = " ".join(lines[:12])
    return "CREDIT MEMO" in header


def _wurth_value_after(lines, label):
    for i, line in enumerate(lines):
        if line == label and i + 1 < len(lines):
            nxt = lines[i + 1]
            if label == "TOTAL AMOUNT" and not _AMOUNT_RE.match(nxt):
                continue
            return nxt
    return None


def _wurth_totals_from_lines(lines):
    """
    Parse subtotal, optional energy fee, and total from Wurth footer layout.

    Many invoices stack values under ``ENERGY FEE`` (subtotal then fee) before
    ``TOTAL AMOUNT``.
    """
    total = None
    subtotal = None
    energy_fee = None

    try:
        ti = lines.index("TOTAL AMOUNT")
        if ti + 1 < len(lines) and _AMOUNT_RE.match(lines[ti + 1]):
            total = to_float(lines[ti + 1])
    except ValueError:
        pass

    try:
        ei = lines.index("ENERGY FEE")
        nums = []
        for line in lines[ei + 1 : ei + 6]:
            if line == "TOTAL AMOUNT":
                break
            if _AMOUNT_RE.match(line):
                nums.append(to_float(line))
        if len(nums) >= 2:
            subtotal, energy_fee = nums[0], nums[1]
        elif len(nums) == 1:
            subtotal = nums[0]
    except ValueError:
        pass

    if subtotal is None:
        try:
            si = lines.index("SUBTOTAL")
            for line in lines[si + 1 : si + 4]:
                if line in _WURTH_COLUMN_HEADERS:
                    break
                if _AMOUNT_RE.match(line):
                    subtotal = to_float(line)
                    break
        except ValueError:
            pass

    if subtotal is None and total is not None and energy_fee is None:
        subtotal = total

    return subtotal, energy_fee, total


def _wurth_collect_column(lines, header, *, stop_prefixes=()):
    try:
        start = lines.index(header)
    except ValueError:
        return []
    values = []
    for line in lines[start + 1 :]:
        if line in _WURTH_COLUMN_HEADERS:
            break
        if any(line.startswith(prefix) for prefix in stop_prefixes):
            break
        values.append(line)
    return values


def _wurth_is_meta_description_line(line):
    """Disclaimer, sales-order footer, or other non-product text in DESCRIPTION column."""
    if not line:
        return True
    if line.startswith("Sales Order") or line.startswith("Delivery note"):
        return True
    upper = line.upper()
    return any(phrase in upper for phrase in _DISCLAIMER_PHRASES)


def _wurth_y_positions(page, texts):
    """Map exact line text to vertical position on the page."""
    wanted = set(texts)
    positions = {}
    for block in page.get_text("dict")["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text in wanted and text not in positions:
                positions[text] = line["bbox"][1]
    return positions


_ROW_Y_TOLERANCE = 2.0


def _wurth_align_descriptions_by_row(page, part_numbers, product_desc_lines):
    """
    Match each part number to the description on the same PDF row (shared Y coordinate).

    Columnar text extraction order often disagrees with row order; Y alignment is reliable.
    """
    if not product_desc_lines:
        return []

    part_ys = _wurth_y_positions(page, part_numbers)
    desc_ys = _wurth_y_positions(page, product_desc_lines)
    used = set()
    aligned = []

    for part in part_numbers:
        py = part_ys.get(part)
        best_desc = None
        best_index = None
        best_delta = None
        for index, desc in enumerate(product_desc_lines):
            if index in used:
                continue
            dy = desc_ys.get(desc)
            if py is None or dy is None:
                continue
            delta = abs(py - dy)
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_index = index
                best_desc = desc
        if best_index is not None and best_delta is not None and best_delta <= _ROW_Y_TOLERANCE:
            used.add(best_index)
            aligned.append(best_desc)
        else:
            aligned.append(None)

    if all(aligned):
        return aligned

    remaining = [
        product_desc_lines[index]
        for index in range(len(product_desc_lines))
        if index not in used
    ]
    fill_iter = iter(remaining)
    return [desc if desc is not None else next(fill_iter, "") for desc in aligned]


def _wurth_product_descriptions(lines, part_numbers, pdf_path=None, page_index=0):
    """Product descriptions aligned to each part number row."""
    raw = _wurth_collect_column(
        lines,
        "DESCRIPTION",
        stop_prefixes=("Sales Order", "Delivery note"),
    )
    product = [line for line in raw if not _wurth_is_meta_description_line(line)]
    if not product:
        return product

    if pdf_path and part_numbers:
        doc = fitz.open(pdf_path)
        try:
            product = _wurth_align_descriptions_by_row(
                doc[page_index], part_numbers, product
            )
        finally:
            doc.close()
    elif raw and _wurth_is_meta_description_line(raw[0]):
        product = list(reversed(product))

    part_count = len(part_numbers)
    if part_count and len(product) > part_count:
        product = product[:part_count]
    return product


def _wurth_line_qty(qty_ord, qty_ship, unit_price, total_price, index):
    """Prefer qty implied by amount ÷ unit price; fall back to QTY ORD then QTY SHIP."""
    up = to_float(unit_price)
    tp = to_float(total_price)
    if up > 0 and tp:
        implied = round(abs(tp) / up)
        if implied >= 1:
            return str(implied)
    if index < len(qty_ord):
        return qty_ord[index]
    if index < len(qty_ship):
        return qty_ship[index]
    return "1"


def _wurth_parse_line_items(lines, pdf_path=None, page_index=0):
    """
    Wurth PDFs use columnar text: all part numbers, then descriptions, then prices.

    Descriptions may be reversed and include disclaimer lines; qty columns can disagree.
    """
    part_numbers = [
        part for part in _wurth_collect_column(lines, "PART NUMBER")
        if _PART_NUMBER_RE.match(part)
    ]
    qty_ord = _wurth_collect_column(lines, "QTY ORD")
    qty_ship = _wurth_collect_column(lines, "QTY SHIP")
    descriptions = _wurth_product_descriptions(
        lines, part_numbers, pdf_path=pdf_path, page_index=page_index
    )
    unit_prices = _wurth_collect_column(lines, "UNIT PRICE")
    amounts = _wurth_collect_column(lines, "AMOUNT")
    units = _wurth_collect_column(lines, "U/M")

    items = []
    for i, part in enumerate(part_numbers):
        desc = descriptions[i] if i < len(descriptions) else ""
        unit = units[i] if i < len(units) else ""
        unit_price = unit_prices[i] if i < len(unit_prices) else 0
        total_price = amounts[i] if i < len(amounts) else 0
        qty = _wurth_line_qty(qty_ord, qty_ship, unit_price, total_price, i)
        items.append(
            make_line_item(
                item_id=part,
                name=desc or part,
                description=desc,
                qty=qty,
                unit=unit,
                unit_price=unit_price,
                total_price=total_price,
            )
        )
    return items


def _wurth_fill_metadata(result, lines):
    result["vendor_name"] = _WURTH_VENDOR
    result["invoice_number"] = _wurth_value_after(lines, "INVOICE #")
    result["date_ordered"] = _wurth_value_after(lines, "INVOICE DATE")
    result["invoice_due_date"] = _wurth_value_after(lines, "DUE DATE")

    po = _wurth_value_after(lines, "PURCHASE ORDER #")
    job = None
    try:
        job_idx = lines.index("JOB NAME")
        if job_idx + 1 < len(lines) and lines[job_idx + 1] != "TERMS":
            job = lines[job_idx + 1]
    except ValueError:
        pass
    if po and job:
        result["cust_po"] = f"{po} / {job}"
    elif po:
        result["cust_po"] = po
    elif job:
        result["cust_po"] = job

    subtotal, energy_fee, total = _wurth_totals_from_lines(lines)
    if total is not None:
        result["invoice_total"] = str(total)
    elif subtotal is not None and energy_fee is not None:
        result["invoice_total"] = str(subtotal + energy_fee)


def parse_wurth_page(lines, pdf_path=None, page_index=0):
    """Parse one page of line-oriented Wurth invoice text."""
    result = empty_invoice(_WURTH_VENDOR)
    _wurth_fill_metadata(result, lines)
    result["line_items"] = _wurth_parse_line_items(
        lines, pdf_path=pdf_path, page_index=page_index
    )
    return normalize_invoice(result)


def parse_wurth_invoice(pdf_path):
    """
    Wurth Louis and Company (wurthlac.com) columnar invoices.

    PDF text is extracted in columns (all qtys, then all part numbers, etc.).
    Multi-page PDFs bundle one invoice per page; returns ``{"invoices": [...]}``.
    """
    invoices = []
    for page_index in range(_wurth_page_count(pdf_path)):
        lines = _wurth_page_lines(pdf_path, page_index)
        if not _wurth_page_is_invoice(lines):
            continue
        invoices.append(parse_wurth_page(lines, pdf_path, page_index))
    if not invoices:
        lines = _wurth_page_lines(pdf_path, 0)
        invoices = [parse_wurth_page(lines, pdf_path, 0)]
    return invoice_bundle(_WURTH_VENDOR, invoices)


parse_wurth_invoice.name = "Wurth Louis and Company"
