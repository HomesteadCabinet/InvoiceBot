"""Sierra Forest Products stacked line-item parsing."""

import re

from .schema import make_line_item, to_float

_SIERRA_CODE_RE = re.compile(r"^\d{5,7}$")
_SIERRA_UNITS = frozenset({"PC", "MBF", "EA", "LF", "BF", "PKG", "RL", "BX"})
_SIERRA_FOOTER_LINE = re.compile(
    r"^(Sierra Truck|SHIP TO|SOLD TO|ShipVia|Sales Tax|B/O$|Description$|INVOICE$|"
    r"Salesperson|Ext\. Price|Ordered|Page:|Website:|Remit To|THANK YOU|"
    r"FSC-Certification|ALL CLAIMS|OVERDUE|Code$|Simple, Secure|download & pay)",
    re.IGNORECASE,
)


def _sierra_adjust_unit_price(qty, unit_price, ext):
    """Fix pymupdf dropping the decimal in per-MBF prices (e.g. 2990 -> 2.99)."""
    if qty <= 0 or unit_price <= 0 or ext <= 0:
        return unit_price
    if abs(qty * unit_price - ext) <= max(0.05, ext * 0.02):
        return unit_price
    for divisor in (1000, 100, 10):
        adjusted = unit_price / divisor
        if adjusted > 0 and abs(qty * adjusted - ext) <= max(0.05, ext * 0.02):
            return adjusted
    return unit_price


def _sierra_collect_desc_after(lines, code_idx, next_code_idx):
    """Lines after the code until the next item's leading description (not its tail block)."""
    if next_code_idx < len(lines):
        end = max(code_idx + 1, next_code_idx - 8)
        return [
            lines[j].strip()
            for j in range(code_idx + 1, end)
            if lines[j].strip() and lines[j].strip() not in _SIERRA_UNITS
        ]

    parts = []
    j = code_idx + 1
    while j < len(lines):
        stripped = lines[j].strip()
        if not stripped or stripped in _SIERRA_UNITS:
            j += 1
            continue
        if _SIERRA_FOOTER_LINE.match(stripped) or _SIERRA_CODE_RE.match(stripped):
            break
        parts.append(stripped)
        j += 1
    return parts


def _parse_sierra_stacked_line_items(lines):
    """
    Parse Sierra line items from pymupdf columnar text.

    Each item ends with a product code; the seven lines above the code are:
    unit (PC/MBF), ext price, shipped qty, unit price, ordered qty, B/O, ``/``.
    One description line sits before that block; continuation lines follow the code.
    """
    code_indices = [i for i, line in enumerate(lines) if _SIERRA_CODE_RE.match(line)]
    items = []

    for ci, code_idx in enumerate(code_indices):
        if code_idx < 7 or lines[code_idx - 1] != "/":
            continue

        unit = lines[code_idx - 7].strip().upper()
        if unit not in _SIERRA_UNITS:
            continue

        ext = to_float(lines[code_idx - 6])
        shipped = lines[code_idx - 5].replace(",", "").strip()
        unit_price = _sierra_adjust_unit_price(
            to_float(shipped),
            to_float(lines[code_idx - 4]),
            ext,
        )

        next_code_idx = code_indices[ci + 1] if ci + 1 < len(code_indices) else len(lines)

        desc_parts = []
        if code_idx >= 8:
            before = lines[code_idx - 8].strip()
            if before and before not in _SIERRA_UNITS and before != "/":
                desc_parts.append(before)
        desc_parts.extend(_sierra_collect_desc_after(lines, code_idx, next_code_idx))

        name = desc_parts[0] if desc_parts else lines[code_idx]
        description = " ".join(desc_parts[1:]) if len(desc_parts) > 1 else ""

        items.append(
            make_line_item(
                item_id=lines[code_idx],
                name=name,
                description=description,
                qty=shipped or "1",
                unit=unit,
                unit_price=unit_price,
                total_price=ext,
            )
        )

    return items
