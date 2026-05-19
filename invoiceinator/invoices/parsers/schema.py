"""Standard invoice schema: fields, normalization, line items."""

import re

INVOICE_FIELDS = (
    "invoice_number",
    "ship_date",
    "date_ordered",
    "vendor_name",
    "invoice_total",
    "invoice_due_date",
    "cust_po",
    "line_items",
)

# Standard parser/API result: one or more invoices (single-page PDFs use length 1).
PARSER_OUTPUT_FIELDS = ("vendor_name", "invoices")

LINE_ITEM_ALIASES = {
    "id": ("id", "Id", "item_code", "Item Code", "Article No.", "article_no", "POS", "pos"),
    "name": ("name", "Name"),
    "description": ("description", "Description"),
    "qty": ("qty", "Qty", "quantity", "Quantity"),
    "unit": ("unit", "Unit", "uom", "UOM"),
    "unit_price": ("unit_price", "Unit_Price", "Unit Price (USD)", "unit price"),
    "total_price": ("total_price", "Total_Price", "Amount (USD)", "amount", "total price"),
    "width": ("width", "Width"),
    "length": ("length", "Length"),
    "height": ("height", "Height"),
    "job": ("job", "Job", "job_name"),
    "job_id": ("job_id", "Job ID", "Job Id"),
}

HEADER_ALIASES = {
    "invoice_number": ("invoice_number", "Invoice Number", "invoice number"),
    "ship_date": ("ship_date", "Ship Date"),
    "date_ordered": ("date_ordered", "Date Ordered", "date ordered"),
    "vendor_name": ("vendor_name", "Vendor Name"),
    "invoice_total": ("invoice_total", "Invoice Total"),
    "invoice_due_date": ("invoice_due_date", "Invoice Due Date"),
    "cust_po": ("cust_po", "Cust PO", "cust po"),
    "line_items": ("line_items", "Line Items"),
}


def empty_invoice(vendor_name):
    return {
        "invoice_number": None,
        "ship_date": None,
        "date_ordered": None,
        "vendor_name": vendor_name,
        "invoice_total": None,
        "invoice_due_date": None,
        "cust_po": None,
        "line_items": [],
    }


def to_float(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("$", "").replace(",", "")
    if not s:
        return 0.0
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    if s.startswith("."):
        s = "0" + s
    try:
        return float(s)
    except ValueError:
        return 0.0


def normalize_dimension(value):
    """
    Round fractional inch measurements to 4 decimal places and drop trailing zeros.

    Examples: ``19.3750`` → ``19.375``, ``14.0`` → ``14``, ``11.875`` → ``11.875``.
    """
    if value is None:
        return None
    try:
        rounded = round(float(value), 4)
    except (TypeError, ValueError):
        return None
    text = f"{rounded:.4f}".rstrip("0").rstrip(".")
    if not text or text == "-":
        return 0
    if "." in text:
        return float(text)
    return int(text)


def pdf_lines(pdf_path):
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    return [line.strip() for line in text.splitlines() if line.strip()]


def pdf_text(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def value_after(lines, label):
    for i, line in enumerate(lines):
        if label.lower() in line.lower():
            parts = re.split(re.escape(label), line, flags=re.IGNORECASE, maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
            if i + 1 < len(lines):
                return lines[i + 1]
    return None


# 48.5" x 120.5", 49"x97", 4'x8', etc.
_PANEL_DIMENSION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r'(?:["\u201d]|(?:\s*(?:in|inch|inches)\b)?)'
    r"\s*[xX×]\s*"
    r"(\d+(?:\.\d+)?)\s*"
    r'(?:["\u201d]|(?:\s*(?:in|inch|inches)\b)?)',
    re.IGNORECASE,
)
_PANEL_DIMENSION_FEET_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*['\u2019]\s*[xX×]\s*(\d+(?:\.\d+)?)\s*['\u2019]?",
    re.IGNORECASE,
)


def extract_panel_dimensions(*texts):
    """
    Parse panel width × length (inches) from product text.

    Examples: ``48.5" x 120.5"``, ``49"x97"``, ``4'x8'`` (feet converted to inches).
    Returns ``(width, length)`` or ``(None, None)``.
    """
    combined = " ".join(str(t) for t in texts if t).strip()
    if not combined:
        return None, None

    m = _PANEL_DIMENSION_RE.search(combined)
    if m:
        return normalize_dimension(m.group(1)), normalize_dimension(m.group(2))

    m = _PANEL_DIMENSION_FEET_RE.search(combined)
    if m:
        return (
            normalize_dimension(to_float(m.group(1)) * 12),
            normalize_dimension(to_float(m.group(2)) * 12),
        )

    return None, None


def make_line_item(
    *,
    item_id="",
    name="",
    description="",
    job="",
    job_id="",
    qty="1",
    unit="",
    unit_price=0.0,
    total_price=0.0,
    width=None,
    length=None,
    height=None,
):
    # length and height are the same panel dimension (terminology varies by vendor)
    second_dim = length if length is not None else height
    if width is None or second_dim is None:
        parsed_w, parsed_l = extract_panel_dimensions(name, description)
        if width is None:
            width = parsed_w
        if second_dim is None:
            second_dim = parsed_l

    width = normalize_dimension(width)
    second_dim = normalize_dimension(second_dim)

    return {
        "id": str(item_id or ""),
        "name": str(name or ""),
        "description": str(description or ""),
        "job": str(job or ""),
        "job_id": str(job_id or ""),
        "qty": str(qty or "1"),
        "unit": str(unit or ""),
        "unit_price": to_float(unit_price),
        "total_price": to_float(total_price),
        "width": width,
        "length": second_dim,
        "height": second_dim,
    }


ITEM_CODE_RE = re.compile(r"^[A-Z]{2,}-\d+$", re.IGNORECASE)
QTY_UM_LINE_RE = re.compile(r"^\d+\s+\w+$")
STACKED_AMOUNT_RE = re.compile(r"^\d+\.\d{2,4}$")

# Stacked qty/UM invoice blocks (Industrial Tool and Supply, Intermountain, etc.)
_STACKED_BLOCK_PHRASE_STOPS = (
    "DELIVER ON", "SOLD ON", "PLEASE PAY", "PAYMENT METHOD", "SUBTOTAL",
    "TOTAL", "SIGNATURE", "SHIP TO", "REMIT", "THANK YOU", "CUST PICKUP",
    "DESCRIPTION", "AMOUNT", "CUSTOMER", "INVOICE", "SOLD TO", "JOB ADDRESS",
    "ORDER ENTRY", "CASHIER", "SALESPERSON", "BRANCH", "STATION", "SHIPPING",
    "QUANTITY", "DEPOSIT", "CHARGE TO ACCT", "SALES TAX", "PAYMENT METHOD(S)",
    "PLEASE PAY THIS", "PAGE", "CODIE",
)
# Exact line matches only — do not use substring (e.g. "PER" matches inside "4per").
_STACKED_BLOCK_EXACT_STOPS = frozenset({
    "PER", "AMOUNT", "DESCRIPTION", "D", "PRICE", "T", "UM", "ITEM", "QUANTITY",
})


def _stacked_block_line_is_stop(line):
    upper = line.upper().strip()
    if upper in _STACKED_BLOCK_EXACT_STOPS:
        return True
    return any(phrase in upper for phrase in _STACKED_BLOCK_PHRASE_STOPS)


def _stacked_block_total_and_unit_price(amount_values, qty_f):
    """Map extended + unit amounts after the ``Y`` flag (order may vary)."""
    if not amount_values:
        return 0.0, 0.0
    if len(amount_values) == 1:
        v = amount_values[0]
        return v, v
    a, b = amount_values[0], amount_values[-1]
    if qty_f > 1:
        if abs(a - b * qty_f) < 0.05:
            return a, b
        if abs(b - a * qty_f) < 0.05:
            return b, a
    return max(a, b), min(a, b)


def _parse_stacked_qty_um_block(block, unit_map):
    """
    Parse one ``<qty> <UM>`` … ``SOU-######`` … ``Y`` … amounts block.

    PDF text order is typically: description line(s), item code, Y, extended amount,
    repeated UM, unit price (4 decimal places).
    """
    qty, unit = block[0].split(maxsplit=1)
    qty_f = to_float(qty)
    item_id = ""
    description_lines = []
    y_found = False
    amount_values = []

    for line in block[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if ITEM_CODE_RE.match(stripped):
            item_id = stripped.upper()
            continue
        if stripped == "Y":
            y_found = True
            continue
        if y_found and STACKED_AMOUNT_RE.match(stripped):
            amount_values.append(float(stripped))
            continue
        if stripped.upper() in unit_map:
            continue
        description_lines.append(stripped)

    total_price, unit_price = _stacked_block_total_and_unit_price(amount_values, qty_f)
    name = description_lines[0] if description_lines else ""
    description = " ".join(description_lines[1:]) if len(description_lines) > 1 else ""
    if not item_id:
        item_id = f"UNSPECIFIED-{qty}-{unit}"

    return make_line_item(
        item_id=item_id,
        name=name,
        description=description,
        qty=qty,
        unit=unit_map.get(unit.upper(), unit),
        unit_price=unit_price,
        total_price=total_price,
    )


def _collect_stacked_qty_um_blocks(lines):
    """Split PDF lines into line-item blocks starting with ``<qty> <UM>``."""
    blocks = []
    i = 0
    while i < len(lines):
        if QTY_UM_LINE_RE.match(lines[i]):
            block = [lines[i]]
            j = i + 1
            while j < len(lines):
                current_line = lines[j]
                if QTY_UM_LINE_RE.match(current_line):
                    break
                if _stacked_block_line_is_stop(current_line):
                    break
                block.append(current_line)
                j += 1
            blocks.append(block)
            i = j
        else:
            i += 1
    return blocks


def _pick_field(raw, aliases):
    for key in aliases:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def normalize_line_item(raw):
    if not isinstance(raw, dict):
        return make_line_item()
    return make_line_item(
        item_id=_pick_field(raw, LINE_ITEM_ALIASES["id"]),
        name=_pick_field(raw, LINE_ITEM_ALIASES["name"]),
        description=_pick_field(raw, LINE_ITEM_ALIASES["description"]),
        job=_pick_field(raw, LINE_ITEM_ALIASES["job"]),
        job_id=_pick_field(raw, LINE_ITEM_ALIASES["job_id"]),
        qty=_pick_field(raw, LINE_ITEM_ALIASES["qty"]) or "1",
        unit=_pick_field(raw, LINE_ITEM_ALIASES["unit"]),
        unit_price=_pick_field(raw, LINE_ITEM_ALIASES["unit_price"]),
        total_price=_pick_field(raw, LINE_ITEM_ALIASES["total_price"]),
        width=_pick_field(raw, LINE_ITEM_ALIASES["width"]),
        length=_pick_field(raw, LINE_ITEM_ALIASES["length"]),
        height=_pick_field(raw, LINE_ITEM_ALIASES["height"]),
    )


def normalize_invoice(data, vendor_name=None):
    """Coerce any parser output into the standard invoice dict."""
    if data is None:
        data = {}
    if hasattr(data, "to_dict"):
        data = {"line_items": data.to_dict("records")}

    result = empty_invoice(
        _pick_field(data, HEADER_ALIASES["vendor_name"])
        or vendor_name
        or ""
    )

    for field in INVOICE_FIELDS:
        if field == "line_items":
            continue
        val = _pick_field(data, HEADER_ALIASES[field])
        if val is not None:
            result[field] = str(val).strip() if field == "invoice_total" and val else val
            if field == "invoice_total" and result[field]:
                m = re.search(r"-?[\d,]+\.\d{2}", str(result[field]))
                if m:
                    result[field] = m.group(0).replace(",", "")

    raw_items = _pick_field(data, HEADER_ALIASES["line_items"]) or []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    result["line_items"] = [normalize_line_item(item) for item in raw_items]
    return result


def invoice_bundle(vendor_name, invoices):
    """Build the standard parser result envelope."""
    return {
        "vendor_name": vendor_name or None,
        "invoices": list(invoices),
    }


def normalize_parser_output(data, vendor_name=None):
    """
    Coerce any parser return value into the standard multi-invoice envelope:

    ``{"vendor_name": "...", "invoices": [<invoice>, ...]}``

    Single-invoice PDFs always produce a one-element ``invoices`` list.
    """
    if isinstance(data, list):
        invoices = [
            normalize_invoice(item, vendor_name) for item in data
        ]
        bundle_vendor = vendor_name or ""
    elif isinstance(data, dict) and "invoices" in data:
        bundle_vendor = data.get("vendor_name") or vendor_name or ""
        invoices = [
            normalize_invoice(item, bundle_vendor or vendor_name)
            for item in data["invoices"]
        ]
    else:
        bundle_vendor = vendor_name or ""
        invoices = [normalize_invoice(data, vendor_name)]

    if not bundle_vendor and invoices:
        bundle_vendor = invoices[0].get("vendor_name") or ""

    return invoice_bundle(bundle_vendor, invoices)
