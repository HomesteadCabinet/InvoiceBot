"""Hafele invoice parser."""

import re

from .pdf import pdf_lines, pdf_text
from .schema import empty_invoice, make_line_item, normalize_invoice, to_float

_ARTICLE_RE = re.compile(r"^\d{3}\.\d{2}\.\d{3}$")
_POS_RE = re.compile(r"^\d{1,2}$")
_QTY_RE = re.compile(r"^\d+$")
_AMOUNT_RE = re.compile(r"^[\d,]+\.\d{2}$")
_PO_NUMBER_RE = re.compile(r"PO Number:\s*(.+)", re.IGNORECASE)
_DESC_STOP_PREFIXES = (
    "HTS:",
    "PO Number:",
    "MERCHANDISE TOTAL",
    "Carry forward",
    "For inquiries",
    "Customer-No",
    "SAP PAGE",
    "Hafele America Co.",
    "Sold to:",
    "Page:",
    "STANDARD TERMS",
    "All Purchase Orders",
)


def _parse_unit_price(raw):
    if not raw:
        return 0.0
    if "free" in raw.lower():
        return 0.0
    return to_float(raw)


def _job_from_po_value(po_value):
    """Parse per-line ``PO Number:`` into job id and name (e.g. ``26294 FMD 31801``)."""
    po_value = (po_value or "").strip()
    if not po_value or po_value.upper() == "SHOP":
        return "", ""
    match = re.match(r"^(\d+)\s*(.*)$", po_value)
    if match:
        return match.group(1), match.group(2).strip()
    return "", ""


def _job_above_line_item(lines, item_index):
    for j in range(item_index - 1, max(-1, item_index - 15), -1):
        match = _PO_NUMBER_RE.search(lines[j])
        if match:
            return _job_from_po_value(match.group(1))
        if _is_line_item_start(lines, j):
            break
    return "", ""


def _cust_po_from_lines(lines):
    """Prefer numeric PO; item blocks often repeat a more specific PO than the header."""
    candidates = []
    for line in lines:
        m = re.search(r"PO Number:\s*(.+)", line, re.IGNORECASE)
        if m:
            candidates.append(m.group(1).strip())
    for po in reversed(candidates):
        m = re.match(r"^(\d+)", po)
        if m:
            return m.group(1)
    for po in reversed(candidates):
        if po.upper() != "SHOP":
            return po.split()[0] if po.split() else po
    return candidates[0] if candidates else None


def _is_line_item_start(lines, i):
    return (
        i + 8 < len(lines)
        and _POS_RE.match(lines[i])
        and _QTY_RE.match(lines[i + 1])
        and _ARTICLE_RE.match(lines[i + 3])
        and lines[i + 4] == "Pack Qty ="
    )


def _collect_description(lines, start):
    parts = []
    j = start
    while j < len(lines):
        line = lines[j]
        if any(line.startswith(prefix) for prefix in _DESC_STOP_PREFIXES):
            break
        if _is_line_item_start(lines, j):
            break
        parts.append(line)
        j += 1
    return " ".join(parts)


def parse_hafele_invoice(pdf_path):
    """Hafele America Co. — multi-page POS/quantity/article invoices."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice("Hafele America Co.")

    for i, line in enumerate(lines):
        if not result["invoice_number"] and line == "Invoice-No":
            for j in range(i + 1, min(i + 6, len(lines))):
                if re.match(r"^\d{6,}$", lines[j]):
                    result["invoice_number"] = lines[j]
                    break
        if not result["date_ordered"] and line == "Date" and i > 0 and lines[i - 1] == "Invoice-No":
            for j in range(i + 1, min(i + 5, len(lines))):
                if re.search(r"[A-Za-z]{3,}.*\d{4}", lines[j]):
                    result["date_ordered"] = lines[j]
                    break

    result["cust_po"] = _cust_po_from_lines(lines)

    m = re.search(r"USD\s*\n\s*([\d,]+\.\d{2})", pdf_text(pdf_path))
    if m:
        result["invoice_total"] = m.group(1).replace(",", "")

    seen_pos = set()
    for i in range(len(lines)):
        if not _is_line_item_start(lines, i):
            continue

        pos = lines[i]
        if pos in seen_pos:
            continue
        seen_pos.add(pos)

        article_no = lines[i + 3]

        qty = lines[i + 1]
        unit = lines[i + 2]
        unit_price = _parse_unit_price(lines[i + 7])
        amount = lines[i + 8]
        if not _AMOUNT_RE.match(amount) and not (amount.replace(",", "").replace(".", "").isdigit()):
            continue

        desc = _collect_description(lines, i + 9)
        job_id, job_name = _job_above_line_item(lines, i)
        result["line_items"].append(
            make_line_item(
                item_id=article_no,
                name=desc.split(",")[0] if desc else article_no,
                description=desc,
                job_id=job_id,
                job=job_name,
                qty=qty,
                unit=unit,
                unit_price=unit_price,
                total_price=amount,
            )
        )

    return normalize_invoice(result)


parse_hafele_invoice.name = "Hafele America Co."
