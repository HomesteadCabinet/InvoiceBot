"""Sierra invoice parser."""

import re

from .camelot_tables import _parse_camelot_code_tables
from .pdf import pdf_lines, pdf_text, value_after
from .schema import empty_invoice, normalize_invoice, to_float
from .sierra_common import _parse_sierra_stacked_line_items


def parse_sierra_invoice(pdf_path):
    """Sierra Forest Products — columnar PDF text with Code / Shipped / Ext. Price blocks."""
    lines = pdf_lines(pdf_path)
    full_text = pdf_text(pdf_path)
    result = empty_invoice("Sierra Forest Products, Inc.")

    inv_match = re.search(r"\bL\d{6,}\b", full_text)
    if inv_match:
        result["invoice_number"] = inv_match.group(0)

    for i, line in enumerate(lines):
        if "Ship Date" in line:
            m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", line)
            if m:
                result["ship_date"] = m.group(0)
            elif i > 0:
                m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", lines[i - 1])
                if m:
                    result["ship_date"] = m.group(0)

    inv_date = value_after(lines, "Inv Date")
    if inv_date:
        m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", inv_date)
        if m and not re.match(r"^L\d+", inv_date):
            result["date_ordered"] = m.group(0)

    all_dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", full_text)
    if not result["date_ordered"] and all_dates:
        exclude = {result.get("ship_date"), result.get("invoice_due_date")}
        order_candidates = [d for d in all_dates if d not in exclude]
        if order_candidates:
            result["date_ordered"] = order_candidates[-1]

    for i, line in enumerate(lines):
        if "Cust. P.O. #" in line or line.strip() == "Cust. P.O. #":
            if i + 1 < len(lines):
                result["cust_po"] = lines[i + 1].strip()
                break

    if not result["invoice_total"]:
        for i, line in enumerate(lines):
            if line.strip().upper() == "TOTAL":
                for j in range(i + 1, min(i + 4, len(lines))):
                    cleaned = lines[j].replace("$", "").strip()
                    if re.match(r"^-?[\d,]+\.\d{2}$", cleaned) and to_float(cleaned) > 0:
                        result["invoice_total"] = cleaned.replace(",", "")
                        break

    due_date_match = re.search(
        r"if paid by\s*(?:[\$\d.]+\s*)?(\d{1,2}/\d{1,2}/\d{4})", full_text, re.IGNORECASE
    )
    if due_date_match:
        result["invoice_due_date"] = due_date_match.group(1)

    result["line_items"] = _parse_sierra_stacked_line_items(lines)
    if not result["line_items"]:
        result["line_items"] = _parse_camelot_code_tables(pdf_path)
    return normalize_invoice(result)


parse_sierra_invoice.name = "Sierra Forest Products"
