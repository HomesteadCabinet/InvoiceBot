"""Industrial Tool Supply invoice parser."""

import re

from difflib import get_close_matches

from .pdf import pdf_lines
from .schema import empty_invoice, normalize_invoice, to_float
from .stacked import ITEM_CODE_RE, QTY_UM_LINE_RE, _collect_stacked_qty_um_blocks, _parse_stacked_qty_um_block


def parse_industrial_tool_supply_invoice(pdf_path):
    """
    Industrial Tool and Supply — stacked qty/UM line blocks (same family as Intermountain).

    Each line item block: ``<qty> <UM>``, description lines, ``SOU-######`` item code,
    ``Y``, then extended amount and per-unit price (order varies by line count).
    """
    lines = pdf_lines(pdf_path)
    result = empty_invoice("Industrial Tool and Supply")

    unit_map = {
        "EA": "Each",
        "BF": "Board Feet",
        "PC": "Piece",
        "MSF": "Thousand Square Feet",
        "MBF": "Thousand Board Feet",
    }

    def fuzzy_line_match(keyword, threshold=0.8):
        for idx, line in enumerate(lines):
            matches = get_close_matches(keyword.lower(), [line.lower()], n=1, cutoff=threshold)
            if matches:
                return idx
        return -1

    inv_match = re.search(r"\b(\d{4}-\d{6})\b", " ".join(lines))
    if inv_match:
        result["invoice_number"] = inv_match.group(1)

    sold_idx = fuzzy_line_match("Sold On")
    if sold_idx != -1:
        for j in range(sold_idx, min(sold_idx + 3, len(lines))):
            m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", lines[j])
            if m:
                result["ship_date"] = m.group(0)
                result["date_ordered"] = m.group(0)
                break

    subtotal_idx = fuzzy_line_match("SubTotal")
    if subtotal_idx != -1:
        for j in range(subtotal_idx + 1, min(subtotal_idx + 8, len(lines))):
            cleaned = lines[j].replace("$", "").strip()
            if re.match(r"^-?[\d,]+\.\d{2}$", cleaned) and to_float(cleaned) > 0:
                result["invoice_total"] = cleaned.replace(",", "")
                break

    # CUSTOMER PO# value (e.g. SHIPPING) — not the numeric ACCOUNT id above the ACCOUNT label.
    for i, line in enumerate(lines):
        if line == "Item" and i + 1 < len(lines):
            po_value = lines[i + 1].strip()
            if po_value and not QTY_UM_LINE_RE.match(po_value) and not ITEM_CODE_RE.match(po_value):
                result["cust_po"] = po_value
                break

    for block in _collect_stacked_qty_um_blocks(lines):
        try:
            result["line_items"].append(_parse_stacked_qty_um_block(block, unit_map))
        except Exception:
            continue

    return normalize_invoice(result)


parse_industrial_tool_supply_invoice.name = "Industrial Tool and Supply"
