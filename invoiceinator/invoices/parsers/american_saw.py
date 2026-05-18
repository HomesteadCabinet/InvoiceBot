"""American Saw invoice parser."""

import re

from .pdf import pdf_lines, value_after
from .schema import empty_invoice, make_line_item, normalize_invoice


def parse_american_saw_invoice(pdf_path):
    """American Saw & Hammering Inc. — simple code/description/qty/price table (generic.pdf)."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice("American Saw & Hammering Inc.")

    result["date_ordered"] = value_after(lines, "Date")
    inv = value_after(lines, "Invoice #")
    if inv:
        result["invoice_number"] = inv.split()[0] if " " in inv else inv
    result["ship_date"] = value_after(lines, "Ship")
    result["cust_po"] = value_after(lines, "P.O. Number")

    try:
        idx = lines.index("Amount") + 1
    except ValueError:
        return normalize_invoice(result)

    i = idx
    while i + 4 < len(lines):
        code = lines[i]
        desc = lines[i + 1]
        qty = lines[i + 2]
        unit_price = lines[i + 3]
        total = lines[i + 4]
        if not re.match(r"^[\d.]+$", qty):
            break
        result["line_items"].append(
            make_line_item(
                item_id=code,
                name=desc,
                description=desc,
                qty=qty,
                unit_price=unit_price,
                total_price=total,
            )
        )
        i += 5

    if result["line_items"]:
        result["invoice_total"] = f"{sum(item['total_price'] for item in result['line_items']):.2f}"

    return normalize_invoice(result)


parse_american_saw_invoice.name = "American Saw & Hammering"
