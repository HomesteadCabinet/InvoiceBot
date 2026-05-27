"""Stacked qty/UM invoice line blocks (Industrial Tool, etc.)."""

import re

from .schema import make_line_item, normalize_quantity, to_float

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
    qty = normalize_quantity(qty)
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
