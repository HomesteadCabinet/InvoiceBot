"""Hafele invoice parser."""

import re

from .pdf import pdf_lines, pdf_text
from .schema import empty_invoice, make_line_item, normalize_invoice, to_float


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
        if not result["cust_po"] and "PO Number:" in line:
            m = re.search(r"PO Number:\s*(\d+)", line)
            if m:
                result["cust_po"] = m.group(1)
        if not result["invoice_total"] and re.match(r"^[\d,]+\.\d{2}$", line):
            # Last page total often appears near USD lines; prefer larger totals
            val = to_float(line)
            if val > to_float(result["invoice_total"] or 0):
                result["invoice_total"] = f"{val:.2f}"

    m = re.search(r"USD\s*\n\s*([\d,]+\.\d{2})", pdf_text(pdf_path))
    if m:
        result["invoice_total"] = m.group(1).replace(",", "")

    current_po = result["cust_po"]
    i = 0
    while i < len(lines):
        line = lines[i]
        if "PO Number:" in line:
            m = re.search(r"PO Number:\s*(\d+)", line)
            if m:
                current_po = m.group(1)
            i += 1
            continue

        if re.match(r"^\d{1,2}$", line):
            try:
                pos = line
                qty = lines[i + 1]
                unit = lines[i + 2]
                article_no = lines[i + 3]
                unit_price = lines[i + 6]
                amount = lines[i + 7]
                if not re.match(r"^\d+(\.\d+)?$", unit_price) or not re.match(r"^\d+(\.\d+)?$", amount):
                    i += 1
                    continue

                description_lines = []
                j = i + 8
                while j < len(lines):
                    desc_line = lines[j]
                    if not desc_line or desc_line.startswith("HTS:") or re.match(r"^\d{1,2}$", desc_line):
                        break
                    if desc_line.startswith("PO Number:"):
                        break
                    description_lines.append(desc_line)
                    j += 1

                desc = " ".join(description_lines)
                result["line_items"].append(
                    make_line_item(
                        item_id=article_no,
                        name=desc.split(",")[0] if desc else article_no,
                        description=desc,
                        qty=qty,
                        unit=unit,
                        unit_price=unit_price,
                        total_price=amount,
                    )
                )
                i = j
                continue
            except (IndexError, ValueError):
                pass
        i += 1

    return normalize_invoice(result)


parse_hafele_invoice.name = "Hafele America Co."
