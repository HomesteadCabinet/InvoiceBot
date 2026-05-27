"""Element Designs invoice parser."""

import re

from .pdf import pdf_lines
from .schema import empty_invoice, make_line_item, normalize_dimension, normalize_invoice, to_float

_VENDOR = "Element Designs"

_ITEM_START_RE = re.compile(r"^(\d+)\s+(.+)$")
_DIM_RE = re.compile(r"^\d+\.\d+$")
_QTY_RE = re.compile(r"^\d+$")

_CUSTOMER_HEADER_LABELS = frozenset({
    "Customer PO",
    "Payment Terms",
    "Due Date",
    "Discount Type",
})

_SHIP_HEADER_LABELS = frozenset({
    "Ship Date",
    "Ship Method",
    "FOB",
    "Sales Rep",
    "Code",
    "Shipment Tracking",
})


def _parse_amount_line(line):
    cleaned = line.replace(" ", "").replace(",", "")
    m = re.match(r"^\$(-?)([\d,]+\.\d{2})$", cleaned)
    if not m:
        return None
    val = to_float(m.group(2))
    if m.group(1) == "-":
        val = -val
    return val


def _read_amount(lines, index):
    line = lines[index].strip()
    amount = _parse_amount_line(line)
    if amount is not None:
        return amount, index + 1
    if line in ("$ -", "$-"):
        return -to_float(lines[index + 1]), index + 2
    raise ValueError(f"unrecognized amount line: {line!r}")


def _assign_header_values(labels, values):
    if not labels:
        return {}
    if len(values) <= len(labels):
        return dict(zip(labels, values))
    extra = len(values) - len(labels)
    first_parts = values[: 1 + extra]
    if first_parts[0].rstrip().endswith("-"):
        merged = first_parts[0].rstrip() + first_parts[1].lstrip()
        if len(first_parts) > 2:
            merged = " ".join([merged, *first_parts[2:]])
    else:
        merged = " ".join(first_parts).strip()
    out = {labels[0]: merged}
    for label, value in zip(labels[1:], values[1 + extra :]):
        out[label] = value
    return out


def _parse_labeled_row(lines, start_label, known_labels, stop_labels, *, cap_values=False):
    try:
        start = lines.index(start_label)
    except ValueError:
        return {}

    labels = []
    i = start
    while i < len(lines) and lines[i] in known_labels:
        labels.append(lines[i])
        i += 1

    if not labels or i >= len(lines):
        return {}

    if lines[i] == "#":
        i += 1

    values = []
    while i < len(lines) and lines[i] not in stop_labels:
        if cap_values and len(values) >= len(labels):
            break
        values.append(lines[i])
        i += 1

    return _assign_header_values(labels, values)


def _split_job_from_po(cust_po):
    if not cust_po:
        return "", ""
    lead = cust_po.split("/")[0].strip()
    m = re.match(r"^(\d+)-(.+)$", lead)
    if m:
        return m.group(1), m.group(2).strip()
    return "", ""


def _parse_invoice_header(lines, result):
    inv_match = re.search(r"Invoice\s*:\s*(\S+)", " ".join(lines[:15]))
    if inv_match:
        result["invoice_number"] = inv_match.group(1)

    date_match = re.search(r"Date:\s*(\d{1,2}/\d{1,2}/\d{4})", lines[0] if lines else "")
    if date_match:
        result["date_ordered"] = date_match.group(1)

    customer_fields = _parse_labeled_row(
        lines,
        "Customer PO",
        _CUSTOMER_HEADER_LABELS,
        _SHIP_HEADER_LABELS | {"Profile:"},
    )
    cust_po = customer_fields.get("Customer PO", "")
    result["cust_po"] = cust_po
    result["invoice_due_date"] = customer_fields.get("Due Date")

    job_id, job = _split_job_from_po(cust_po)
    result["_job_id"] = job_id
    result["_job"] = job

    ship_fields = _parse_labeled_row(
        lines, "Ship Date", _SHIP_HEADER_LABELS, {"Profile:"}, cap_values=True
    )
    ship_date = ship_fields.get("Ship Date")
    if ship_date:
        result["ship_date"] = ship_date

    for i, line in enumerate(lines):
        if line == "Total :" and i + 1 < len(lines):
            amount = _parse_amount_line(lines[i + 1])
            if amount is not None:
                result["invoice_total"] = str(amount)
            break


def _line_items_start(lines):
    for i, line in enumerate(lines):
        if line == "Sub Total" and i > 0 and lines[i - 1] == "Price":
            return i + 1
    return None


def _is_item_start(line):
    return bool(_ITEM_START_RE.match(line))


def _at_qty(lines, index):
    return (
        index < len(lines)
        and _QTY_RE.match(lines[index])
        and index + 1 < len(lines)
        and lines[index + 1].strip().startswith("$")
    )


def _item_continues(item_parts, line):
    if item_parts[-1].rstrip().endswith("-"):
        return True
    joined = " ".join(item_parts)
    if line == joined:
        return False
    return len(line.split()) <= 2 and not line.startswith("(")


def _parse_line_items(lines):
    start = _line_items_start(lines)
    if start is None:
        return []

    items = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line in ("Special Instructions", "Sub Total :", "Page 1 of 1"):
            break
        if not _is_item_start(line):
            i += 1
            continue

        line_no, item_name = _ITEM_START_RE.match(line).groups()
        i += 1

        width = length = None
        description_parts = []

        if i + 1 < len(lines) and _DIM_RE.match(lines[i]) and _DIM_RE.match(lines[i + 1]):
            width = normalize_dimension(lines[i])
            length = normalize_dimension(lines[i + 1])
            i += 2
            if i < len(lines) and not _is_item_start(lines[i]) and not _at_qty(lines, i):
                description_parts.append(lines[i])
                i += 1
        else:
            item_parts = [item_name]
            while i < len(lines) and _item_continues(item_parts, lines[i]):
                item_parts.append(lines[i])
                i += 1
            item_name = " ".join(item_parts).strip()

            while i < len(lines):
                if _is_item_start(lines[i]) or _at_qty(lines, i):
                    break
                if lines[i] in ("Special Instructions", "Sub Total :"):
                    break
                description_parts.append(lines[i])
                i += 1

        if not _at_qty(lines, i):
            continue

        qty = lines[i]
        i += 1
        unit_price, i = _read_amount(lines, i)
        total_price, i = _read_amount(lines, i)

        description = " ".join(description_parts).strip()
        name = item_name or description
        if description and description != name:
            pass
        elif description:
            description = ""

        item_id = item_name
        if re.match(r"^Door\b", item_name, re.I):
            item_id = f"{line_no}-{item_name}"

        items.append(
            make_line_item(
                item_id=item_id,
                name=name,
                description=description,
                qty=qty,
                unit="Each",
                unit_price=unit_price,
                total_price=total_price,
                width=width,
                length=length,
                height=length,
            )
        )

    return items


def parse_element_designs_invoice(pdf_path):
    """Element Designs Inc. — door, hardware, and shipping line items with W×H when present."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice(_VENDOR)
    _parse_invoice_header(lines, result)
    result["line_items"] = _parse_line_items(lines)

    job_id = result.pop("_job_id", "")
    job = result.pop("_job", "")
    if job_id or job:
        for item in result["line_items"]:
            if not item.get("job_id"):
                item["job_id"] = job_id
            if not item.get("job") and job:
                item["job"] = job

    return normalize_invoice(result)


parse_element_designs_invoice.name = "Element Designs"
