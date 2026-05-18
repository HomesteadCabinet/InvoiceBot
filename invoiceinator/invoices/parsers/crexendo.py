"""Crexendo invoice parser."""

import re

from .pdf import pdf_lines
from .schema import empty_invoice, make_line_item, normalize_invoice


def parse_crexendo_invoice(pdf_path):
    """Crexendo Business Solutions VoIP bills."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice("Crexendo Business Solutions")

    for line in lines:
        if not result["invoice_number"]:
            m = re.search(r"Bill#\s*(\d+)", line)
            if m:
                result["invoice_number"] = m.group(1)
        if not result["date_ordered"]:
            m = re.search(r"Bill Date:\s*(\d{1,2}/\d{1,2}/\d{2,4})", line)
            if m:
                result["date_ordered"] = m.group(1)
        if not result["invoice_due_date"]:
            m = re.search(r"^Due:\s*(.+)$", line)
            if m:
                result["invoice_due_date"] = m.group(1).strip()
        if not result["invoice_total"]:
            m = re.search(r"^Total:\s*\$?([\d,]+\.\d{2})", line)
            if m:
                result["invoice_total"] = m.group(1).replace(",", "")
        if not result["cust_po"]:
            m = re.search(r"Customer#\s*(\d+)", line)
            if m:
                result["cust_po"] = m.group(1)

    section_indices = [i for i, ln in enumerate(lines) if ln == "Recurring Charges"]
    if not section_indices:
        return normalize_invoice(result)
    start_idx = section_indices[-1]

    try:
        header_end = next(i for i in range(start_idx, len(lines)) if lines[i] == "Amount")
    except StopIteration:
        return normalize_invoice(result)

    date_pat = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
    i = header_end + 1
    while i < len(lines):
        if lines[i].lower().startswith("subtotal"):
            break
        if i + 5 < len(lines) and date_pat.match(lines[i + 1]) and date_pat.match(lines[i + 2]):
            desc, start, end = lines[i], lines[i + 1], lines[i + 2]
            rate, qty, amount = lines[i + 3], lines[i + 4], lines[i + 5]
            result["line_items"].append(
                make_line_item(
                    name=desc,
                    description=f"{start} - {end}",
                    qty=qty,
                    unit_price=rate,
                    total_price=amount,
                )
            )
            i += 6
            continue
        i += 1

    return normalize_invoice(result)


parse_crexendo_invoice.name = "Crexendo Business Solutions"
