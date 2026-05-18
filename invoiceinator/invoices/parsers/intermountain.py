"""Intermountain invoice parser."""

import re

from difflib import get_close_matches

from .pdf import pdf_lines
from .schema import empty_invoice, make_line_item, normalize_invoice, to_float


def parse_intermountain_invoice(pdf_path):
    """Intermountain Wood Products — block-style lumber invoices (im*.pdf)."""
    lines = pdf_lines(pdf_path)
    result = empty_invoice("Intermountain Wood Products")

    unit_map = {
        "EA": "Each",
        "BF": "Board Feet",
        "PC": "Piece",
        "MSF": "Thousand Square Feet",
        "MBF": "Thousand Board Feet",
    }
    block_stopwords = {
        "DELIVER ON", "SOLD ON", "PLEASE PAY", "PAYMENT METHOD", "SUBTOTAL",
        "TOTAL", "SIGNATURE", "SHIP TO", "REMIT", "THANK YOU",
    }

    def fuzzy_line_match(keyword, threshold=0.8):
        for idx, line in enumerate(lines):
            matches = get_close_matches(keyword.lower(), [line.lower()], n=1, cutoff=threshold)
            if matches:
                return idx
        return -1

    for i, line in enumerate(lines):
        if not result["invoice_number"]:
            m = re.search(r"Invoice[#\s]*(\S+)", line)
            if m:
                result["invoice_number"] = m.group(1)
            else:
                m = re.match(r"^(\d{4}-[A-Z]\d+)", line)
                if m:
                    result["invoice_number"] = m.group(1)

        if not result["ship_date"]:
            idx = fuzzy_line_match("Sold On")
            if idx != -1:
                date_match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", lines[idx])
                if date_match:
                    result["ship_date"] = date_match.group(0)

        if not result["invoice_due_date"] and "due" in line.lower():
            m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", line)
            if m:
                result["invoice_due_date"] = m.group(1)

        if not result["invoice_total"]:
            idx = fuzzy_line_match("SubTotal")
            if idx != -1:
                for j in range(idx + 1, min(idx + 8, len(lines))):
                    cleaned = lines[j].replace("$", "").strip()
                    if re.match(r"^-?[\d,]+\.\d{2}$", cleaned) and to_float(cleaned) > 0:
                        result["invoice_total"] = cleaned.replace(",", "")
                        break
            if not result["invoice_total"] and idx != -1:
                result["invoice_total"] = "0.00"
            if not result["invoice_total"]:
                m = re.search(
                    r"Invoice Total of\s*([\d,]+\.\d{2})",
                    " ".join(lines),
                    re.IGNORECASE,
                )
                if m:
                    result["invoice_total"] = m.group(1).replace(",", "")

        if not result["cust_po"] and "Customer PO" in line and i + 1 < len(lines):
            result["cust_po"] = lines[i + 1].strip()

    item_blocks = []
    i = 0
    while i < len(lines):
        if re.match(r"^\d+\s+\w+$", lines[i]):
            block = [lines[i]]
            j = i + 1
            while j < len(lines):
                current_line = lines[j]
                if re.match(r"^\d+\s+\w+$", current_line):
                    break
                if any(stop in current_line.upper() for stop in block_stopwords):
                    break
                block.append(current_line)
                j += 1
            item_blocks.append(block)
            i = j
        else:
            i += 1

    for block in item_blocks:
        try:
            qty, unit = block[0].split()
            item_id = ""
            description_lines = []
            unit_price = 0.0
            total_price = 0.0
            y_found = False

            for line in block:
                m = re.match(r"([A-Z]{3,}[0-9\-]+)", line.strip())
                if m:
                    item_id = m.group(1)
                    break

            for line in block[1:]:
                stripped = line.strip()
                if stripped == "Y":
                    y_found = True
                elif y_found and re.match(r"^\d+\.\d{2}$", stripped):
                    unit_price = float(stripped)
                elif unit_price and re.match(r"^\d+\.\d{4}$", stripped):
                    total_price = float(stripped)
                elif re.match(r"^\d+\.\d{2}[A-Z]+\d+\.\d{4}$", stripped):
                    amt_match = re.match(r"^(\d+\.\d{2})([A-Z]+)(\d+\.\d{4})$", stripped)
                    if amt_match:
                        unit_price = float(amt_match.group(1))
                        total_price = float(amt_match.group(3))
                        unit = unit_map.get(amt_match.group(2), amt_match.group(2))
                elif stripped:
                    description_lines.append(stripped)

            name = description_lines[0] if description_lines else ""
            description = " ".join(description_lines[1:]) if len(description_lines) > 1 else ""
            if not item_id or item_id in ("UM", "JOB", "STC", "COMMENT"):
                item_id = f"UNSPECIFIED-{qty}-{unit}"

            result["line_items"].append(
                make_line_item(
                    item_id=item_id,
                    name=name,
                    description=description,
                    qty=qty,
                    unit=unit_map.get(unit.upper(), unit),
                    unit_price=unit_price,
                    total_price=total_price,
                )
            )
        except Exception:
            continue

    return normalize_invoice(result)


parse_intermountain_invoice.name = "Intermountain Wood Products"
