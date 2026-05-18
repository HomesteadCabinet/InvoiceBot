"""Bitdefender invoice parser."""

import re

from .pdf import pdf_lines
from .schema import empty_invoice, make_line_item, normalize_invoice


def parse_bitdefender_invoice(pdf_path):
    """Bitdefender invoices via Avangate/2Checkout."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice("Bitdefender")

    for line in lines:
        if not result["invoice_number"]:
            m = re.search(r"Invoice No:\s*(\S+)", line)
            if m:
                result["invoice_number"] = m.group(1)
        if not result["ship_date"]:
            m = re.search(r"Delivery date:\s*(\d{4}-\d{2}-\d{2})", line)
            if m:
                result["ship_date"] = m.group(1)
        if not result["date_ordered"]:
            m = re.match(r"^Date:\s*(.+)$", line)
            if m:
                result["date_ordered"] = m.group(1).strip()
        if not result["invoice_total"]:
            m = re.search(r"Total\s*\(USD\):\s*([\d,]+\.\d{2})", line)
            if m:
                result["invoice_total"] = m.group(1).replace(",", "")
        if not result["cust_po"]:
            m = re.search(r"Order No:\s*(\S+)", line)
            if m:
                result["cust_po"] = m.group(1)

    try:
        header_end = next(i for i, ln in enumerate(lines) if ln.startswith("Value (USD)"))
    except StopIteration:
        return normalize_invoice(result)

    end_idx = len(lines)
    for i in range(header_end + 1, len(lines)):
        if "Payment Details" in lines[i]:
            end_idx = i
            break

    decimal_pat = re.compile(r"^\d+(?:\.\d{2})?$")
    int_pat = re.compile(r"^\d+$")

    def clean_description(parts):
        text = " ".join(parts).strip()
        text = re.sub(r"Bitdef\s+ender", "Bitdefender", text)
        return re.sub(r"\s+", " ", text)

    i = header_end + 1
    while i < end_idx:
        if int_pat.match(lines[i]):
            no = lines[i]
            j = i + 1
            desc_parts = []
            while j < end_idx:
                if int_pat.match(lines[j]) and j + 1 < end_idx and decimal_pat.match(lines[j + 1]):
                    break
                desc_parts.append(lines[j])
                j += 1
            if j + 3 >= end_idx:
                break
            units, unit_price, _, value = lines[j], lines[j + 1], lines[j + 2], lines[j + 3]
            description = clean_description(desc_parts)
            result["line_items"].append(
                make_line_item(
                    item_id=no,
                    name=description.split(",")[0] if description else "",
                    description=description,
                    qty=units,
                    unit_price=unit_price,
                    total_price=value,
                )
            )
            i = j + 4
        else:
            i += 1

    return normalize_invoice(result)


parse_bitdefender_invoice.name = "Bitdefender"
