"""High Mountain invoice parser."""

import re

from .pdf import pdf_lines, pdf_text
from .schema import empty_invoice, make_line_item, normalize_invoice, to_float


def parse_high_mountain_invoice(pdf_path):
    """High Mountain Forest Products — stacked column invoices (hm*.pdf)."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice("High Mountain Forest Products")

    inv_nums = re.findall(r"\d{10}-\d{3}", pdf_text(pdf_path))
    if inv_nums:
        result["invoice_number"] = inv_nums[0]

    m = re.search(r"Due Date:\s*(\d{2}/\d{2}/\d{2,4})", pdf_text(pdf_path))
    if m:
        result["invoice_due_date"] = m.group(1)

    for i, line in enumerate(lines):
        if line == "Ship Date:" and i + 1 < len(lines):
            result["ship_date"] = lines[i + 1]
        if line == "Order Date:" and i + 1 < len(lines):
            result["date_ordered"] = lines[i + 1]
        if line.startswith("Job:") or (line == "Job:" and i + 1 < len(lines)):
            result["cust_po"] = line.replace("Job:", "").strip() or (
                lines[i + 1] if i + 1 < len(lines) else None
            )

    text = pdf_text(pdf_path)
    for pattern in (
        r"Balance\s*\n\s*\$?(-?[\d,]+\.\d{2})",
        r"Subtotal\s*\n\s*(-?[\d,]+\.\d{2})",
        r"Printed:.*\n\s*([\d,]+\.\d{2})",
    ):
        m = re.search(pattern, text)
        if m:
            result["invoice_total"] = m.group(1).replace(",", "")
            break

    code_pat = re.compile(r"^[A-Z][A-Z0-9]{4,}$")
    skip_codes = {"CREDITMEMO", "INVOICE", "DELNC", "SALT", "SALES", "PRINTED"}

    i = 0
    while i < len(lines):
        line = lines[i]
        if code_pat.match(line) and line not in skip_codes:
            code = line
            j = i + 1
            qty = "1"
            unit = "PC"
            desc_parts = []
            unit_price = 0.0
            total_price = 0.0
            while j < len(lines) and not lines[j].lower().startswith("subtotal"):
                ln = lines[j]
                if re.match(r"^PC$", ln) and j + 1 < len(lines) and re.match(r"^[\d.]+$", lines[j + 1]):
                    unit = "PC"
                    qty = lines[j + 1].split("/")[0]
                price_m = re.search(r"([\d.]+)/PC", ln)
                if price_m:
                    unit_price = to_float(price_m.group(1))
                if re.search(r"[a-z]", ln) and len(ln) > 4 and not price_m:
                    desc_parts.append(ln)
                if re.match(r"^[\d.]+$", ln) and to_float(ln) > 50:
                    total_price = to_float(ln)
                j += 1
            if desc_parts:
                desc = " ".join(desc_parts)
                if not total_price and unit_price:
                    total_price = unit_price * to_float(qty)
                result["line_items"].append(
                    make_line_item(
                        item_id=code,
                        name=desc_parts[0],
                        description=desc,
                        qty=qty,
                        unit=unit,
                        unit_price=unit_price,
                        total_price=total_price or unit_price,
                    )
                )
            i = j
        else:
            i += 1

    return normalize_invoice(result)


parse_high_mountain_invoice.name = "High Mountain Forest Products"
