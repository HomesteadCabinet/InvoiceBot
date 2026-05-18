"""Wi Fiber invoice parser."""

import re

import pymupdf as fitz

from .pdf import value_after
from .schema import empty_invoice, make_line_item, normalize_invoice, to_float


def parse_wi_fiber_invoice(pdf_path):
    """Wi-Fiber, Inc. recurring service statements."""
    doc = fitz.open(pdf_path)
    pages = [p.get_text().splitlines() for p in doc]
    all_lines = [ln.strip() for page in pages for ln in page if ln.strip()]
    page2_lines = [ln.strip() for ln in pages[1] if ln.strip()] if len(pages) > 1 else []

    result = empty_invoice("Wi-Fiber, Inc.")
    date_re = r"[A-Z][a-z]+\s+\d{1,2}\s+\d{4}"

    stmt = value_after(all_lines, "Statement #")
    if stmt:
        m = re.search(r"\d+", stmt)
        if m:
            result["invoice_number"] = m.group(0)

    stmt_date = value_after(all_lines, "Statement Date")
    if stmt_date:
        m = re.search(date_re, stmt_date)
        result["date_ordered"] = m.group(0) if m else stmt_date

    service = value_after(all_lines, "Service Period")
    if service:
        m = re.search(rf"({date_re})\s+to", service)
        if m:
            result["ship_date"] = m.group(1)

    due = value_after(all_lines, "Due Date")
    if due:
        m = re.search(date_re, due)
        result["invoice_due_date"] = m.group(0) if m else due

    acct = value_after(all_lines, "Account Number")
    if acct:
        m = re.search(r"\d+", acct)
        if m:
            result["cust_po"] = m.group(0)

    for i, line in enumerate(all_lines):
        if line.lower().startswith("total due by") and i + 1 < len(all_lines):
            m = re.search(r"\$([\d,]+\.\d{2})", all_lines[i + 1])
            if m:
                result["invoice_total"] = m.group(1).replace(",", "")
                break
    if not result["invoice_total"]:
        amt = value_after(all_lines, "Amount Due")
        if amt:
            m = re.search(r"\$?([\d,]+\.\d{2})", amt)
            if m:
                result["invoice_total"] = m.group(1).replace(",", "")

    amount_re = re.compile(r"^\(?\$?[\d,]+\.\d{2}\)?$")
    section = None
    i = 0
    while i < len(page2_lines):
        line = page2_lines[i]
        if line in ("Charges", "Credits Applied"):
            section = line
            i += 1
            continue
        if re.match(r"^\d+/\d+$", line):
            i += 1
            continue
        if section and i + 1 < len(page2_lines) and amount_re.match(page2_lines[i + 1]):
            desc = line
            raw_amt = page2_lines[i + 1]
            neg = raw_amt.startswith("(")
            m = re.search(r"([\d,]+\.\d{2})", raw_amt)
            if m:
                val = to_float(m.group(1))
                if neg:
                    val = -val
                qty_match = re.search(r"\bx\s*(\d+)\s*$", desc)
                qty = qty_match.group(1) if qty_match else "1"
                result["line_items"].append(
                    make_line_item(
                        name=desc,
                        description=section,
                        qty=qty,
                        unit_price=val,
                        total_price=val,
                    )
                )
            i += 2
            continue
        i += 1

    return normalize_invoice(result)


parse_wi_fiber_invoice.name = "Wi-Fiber"
