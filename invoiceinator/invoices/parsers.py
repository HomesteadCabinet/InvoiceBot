import camelot
import pandas as pd
import re
import pymupdf as fitz
from difflib import get_close_matches


# You're an expert in Python and PDF parsing using `pdfplumber`, `PyMuPDF`, and `Camelot`.

# I need you to generate a custom parsing function for a vendor invoice. I will provide:
# - The PDF file
# - Key fields I need extracted
# - Notes about how the invoice is structured

# Please return a Python function that:
# - Accepts a `pdf_path` as input
# - Uses `pdfplumber`, `PyMuPDF`, `Camelot` or all of the above to extract structured data
# - Returns a `dict` or `DataFrame` with the extracted fields

# Some fields are repeated across the document, so you will need to be careful to not duplicate them.
# Some fields have a header above the value.
# Methods need to be able to handle irregularly structured invoices.
# Methods need to be able to handle invoices with multiple line items, possibly with multiple pages.
# Each field has our column name and the text to search for in the PDF serparated by a colon.

# Methods need to return these fields along with the line items
# Key fields to extract:
# - Invoice Number:Invoice #
# - Ship Date:Ship Date
# - Date Ordered:Date Ordered
# - Vendor Name: Intermountain Wood Products
# - Invoice Total:Please Pay This Amount
# - Invoice Due Date: Payment Due By
# - Cust PO: Order Name:

# Methods need to return a line items, each with the following fields:
# Line items:
# - Id:ID
# - Name: "Item"
# - Description:
# - Qty:Qty
# - Unit:
# - Unit_Price:Price
# - Total_Price:Total



def parse_allmoxy_invoice(pdf_path):
    doc = fitz.open(pdf_path)
    lines = [
        line.strip()
        for page in doc
        for line in page.get_text().splitlines()
        if line.strip()
    ]

    invoice = {
        "Invoice Number": None,
        "Ship Date": None,
        "Date Ordered": None,
        "Vendor Name": "Intermountain Wood Products",
        "Invoice Total": None,
        "Invoice Due Date": None,
        "Cust PO": None,
        "Line Items": []
    }

    def find_value_after(label):
        for i, line in enumerate(lines):
            if label in line:
                match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", line)
                if match:
                    return match.group(0)
                elif i + 1 < len(lines):
                    return lines[i + 1].strip()
        return None

    # Extract header fields
    invoice["Invoice Number"] = find_value_after("Invoice #")
    invoice["Ship Date"] = find_value_after("Ship Date")
    invoice["Date Ordered"] = find_value_after("Date Ordered")
    invoice["Invoice Due Date"] = find_value_after("Payment Due By")
    invoice["Invoice Total"] = find_value_after("Please Pay This Amount")
    invoice["Cust PO"] = find_value_after("Order Name:")

    # Detect and parse 7-line stacked item blocks
    current_section = None
    i = 0
    header_labels = {"ID", "Qty", "Width", "Height", "Cab #", "Price", "Total"}

    while i < len(lines):
        line = lines[i]

        if line.endswith(":") and "ID" not in line and not line.startswith("Order"):
            current_section = line.rstrip(":").strip()

        if line == "ID":
            # Skip stacked header labels
            while i < len(lines) and lines[i] in header_labels:
                i += 1

            while i + 6 < len(lines):
                block = lines[i:i + 7]
                if any("Total Item" in b or "Total Items" in b for b in block):
                    break

                try:
                    if block[0].lower() not in {"price", "total"} and \
                       block[5].startswith("$") and block[6].startswith("$"):
                        invoice["Line Items"].append({
                            "Id": block[0],
                            "Name": current_section or "Item",
                            "Description": f"{block[2]} x {block[3]}",
                            "Qty": block[1],
                            "Unit": "",
                            "Unit_Price": float(block[5].replace("$", "").replace(",", "")),
                            "Total_Price": float(block[6].replace("$", "").replace(",", ""))
                        })
                        i += 7
                        continue
                except Exception:
                    pass

                i += 1
            continue

        i += 1

    return pd.DataFrame(invoice["Line Items"])
parse_allmoxy_invoice.name = "Allmoxy 1"


def extract_intermountain_invoice_correct_id(pdf_path):
    doc = fitz.open(pdf_path)
    lines = "\n".join([page.get_text() for page in doc]).splitlines()

    result = {
        "Invoice Number": None,
        "Ship Date": None,
        "Vendor Name": "Intermountain Wood Products",
        "Invoice Total": None,
        "Invoice Due Date": None,
        "Cust PO": None,
        "Line Items": []
    }

    unit_map = {
        "EA": "Each", "BF": "Board Feet", "PC": "Piece",
        "MSF": "Thousand Square Feet", "MBF": "Thousand Board Feet"
    }

    block_stopwords = {
        "DELIVER ON", "SOLD ON", "PLEASE PAY", "PAYMENT METHOD", "SUBTOTAL",
        "TOTAL", "SIGNATURE", "SHIP TO", "REMIT", "THANK YOU"
    }

    def fuzzy_line_match(lines, keyword, threshold=0.8):
        for i, line in enumerate(lines):
            matches = get_close_matches(keyword.lower(), [line.lower()], n=1, cutoff=threshold)
            if matches:
                return i, line
        return -1, ""

    # --- Extract header fields ---
    for i, line in enumerate(lines):
        if not result["Invoice Number"]:
            match = re.search(r"Invoice[#\s]*(\w+)", line)
            if match:
                result["Invoice Number"] = match.group(1)
        if not result["Ship Date"]:
            idx, _ = fuzzy_line_match(lines, "Sold On")
            if idx != -1:
                date_match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", lines[idx])
                if date_match:
                    result["Ship Date"] = date_match.group(0)
        if not result["Invoice Due Date"] and "due" in line.lower():
            match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", line)
            if match:
                result["Invoice Due Date"] = match.group(1)
        if not result["Invoice Total"]:
            idx, _ = fuzzy_line_match(lines, "Please Pay This Amount")
            for offset in range(1, 4):
                if idx + offset < len(lines):
                    total_match = re.search(r"(\d{1,3}(,\d{3})*\.\d{2})", lines[idx + offset])
                    if total_match:
                        result["Invoice Total"] = total_match.group(1).replace(",", "")
                        break
        if not result["Cust PO"] and "Customer PO" in line:
            if i + 1 < len(lines):
                result["Cust PO"] = lines[i + 1].strip()

    # --- Parse line item blocks ---
    item_blocks = []
    i = 0
    while i < len(lines):
        if re.match(r"^\d+\s+\w+$", lines[i].strip()):
            block = [lines[i].strip()]
            j = i + 1
            while j < len(lines):
                current_line = lines[j].strip()
                if re.match(r"^\d+\s+\w+$", current_line):
                    break
                if any(stopword in current_line.upper() for stopword in block_stopwords):
                    break
                block.append(current_line)
                j += 1
            item_blocks.append(block)
            i = j
        else:
            i += 1

    # --- Extract fields per item block ---
    for block in item_blocks:
        try:
            qty_unit = block[0]
            qty, unit = qty_unit.split()
            item_id = ""
            name = ""
            description_lines = []
            unit_price = 0.0
            total_price = 0.0
            y_found = False

            # Prefer item code from block before fallback
            for line in block:
                match = re.match(r"([A-Z]{3,}[0-9\-]+)", line.strip())
                if match:
                    item_id = match.group(1)
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

            if description_lines:
                name = description_lines[0]
                description = " ".join(description_lines[1:]) if len(description_lines) > 1 else ""

            if not item_id or item_id in ("UM", "JOB", "STC", "COMMENT"):
                item_id = f"UNSPECIFIED-{qty}-{unit}"

            result["Line Items"].append({
                "Id": item_id,
                "Name": name,
                "Description": description,
                "Qty": qty,
                "Unit": unit_map.get(unit.upper(), unit),
                "Unit_Price": unit_price,
                "Total_Price": total_price
            })
        except Exception:
            continue

    return result
extract_intermountain_invoice_correct_id.name = "Intermountain Wood Products"


def extract_intermountain_invoice_robust(pdf_path):
    doc = fitz.open(pdf_path)
    lines = "\n".join([page.get_text() for page in doc]).splitlines()

    result = {
        "Invoice Number": None,
        "Ship Date": None,
        "Vendor Name": "Intermountain Wood Products",
        "Invoice Total": None,
        "Invoice Due Date": None,
        "Cust PO": None,
        "Line Items": []
    }

    unit_map = {
        "EA": "Each",
        "BF": "Board Feet",
        "PC": "Piece",
        "MSF": "Thousand Square Feet",
        "MBF": "Thousand Board Feet"
    }

    block_stopwords = {
        "DELIVER ON", "SOLD ON", "PLEASE PAY", "PAYMENT METHOD", "SUBTOTAL",
        "TOTAL", "SIGNATURE", "SHIP TO", "REMIT", "THANK YOU"
    }

    def fuzzy_line_match(lines, keyword, threshold=0.8):
        for i, line in enumerate(lines):
            matches = get_close_matches(keyword.lower(), [line.lower()], n=1, cutoff=threshold)
            if matches:
                return i, line
        return -1, ""

    # --- Extract header fields with fuzzy fallback ---
    for i, line in enumerate(lines):
        if not result["Invoice Number"]:
            match = re.search(r"Invoice[#\s]*(\w+)", line)
            if match:
                result["Invoice Number"] = match.group(1)

        if not result["Ship Date"]:
            idx, _ = fuzzy_line_match(lines, "Sold On")
            if idx != -1:
                date_match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", lines[idx])
                if date_match:
                    result["Ship Date"] = date_match.group(0)

        if not result["Invoice Due Date"]:
            if "due" in line.lower():
                match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", line)
                if match:
                    result["Invoice Due Date"] = match.group(1)

        if not result["Invoice Total"]:
            idx, _ = fuzzy_line_match(lines, "Please Pay This Amount")
            for offset in range(1, 4):
                if idx + offset < len(lines):
                    total_match = re.search(r"(\d{1,3}(,\d{3})*\.\d{2})", lines[idx + offset])
                    if total_match:
                        result["Invoice Total"] = total_match.group(1).replace(",", "")
                        break

        if not result["Cust PO"] and "Customer PO" in line:
            if i + 1 < len(lines):
                result["Cust PO"] = lines[i + 1].strip()

    # --- Extract line items ---
    item_blocks = []
    i = 0
    while i < len(lines):
        if re.match(r"^\d+\s+\w+$", lines[i].strip()):
            block = [lines[i].strip()]
            j = i + 1
            while j < len(lines):
                current_line = lines[j].strip()
                # Stop if it's another item or a known footer keyword
                if re.match(r"^\d+\s+\w+$", current_line):
                    break
                if any(stopword in current_line.upper() for stopword in block_stopwords):
                    break
                block.append(current_line)
                j += 1
            item_blocks.append(block)
            i = j
        else:
            i += 1

    for block in item_blocks:
        try:
            qty_unit = block[0]
            qty, unit = qty_unit.split()
            item_id = ""
            name = ""
            description_lines = []
            unit_price = 0.0
            total_price = 0.0
            y_found = False

            for line in block[1:]:
                if re.fullmatch(r"[A-Z0-9\-]{3,}", line):
                    item_id = line
                elif line.strip() == "Y":
                    y_found = True
                elif y_found and re.match(r"^\d+\.\d{2}$", line):
                    unit_price = float(line)
                elif unit_price and re.match(r"^\d+\.\d{4}$", line):
                    total_price = float(line)
                elif re.match(r"^\d+\.\d{2}[A-Z]+\d+\.\d{4}$", line):  # e.g. 42.54MSF1329.4917
                    amt_match = re.match(r"^(\d+\.\d{2})([A-Z]+)(\d+\.\d{4})$", line)
                    if amt_match:
                        unit_price = float(amt_match.group(1))
                        unit_type_inline = amt_match.group(2)
                        total_price = float(amt_match.group(3))
                        unit = unit_map.get(unit_type_inline, unit_type_inline)
                elif line.strip():
                    description_lines.append(line.strip())

            if description_lines:
                name = description_lines[0]
                description = " ".join(description_lines[1:]) if len(description_lines) > 1 else ""

            if item_id in ("UM", "JOB", "STC", ""):
                item_id = f"UNSPECIFIED-{qty}-{unit}"

            result["Line Items"].append({
                "Id": item_id,
                "Name": name,
                "Description": description,
                "Qty": qty,
                "Unit": unit_map.get(unit.upper(), unit),
                "Unit_Price": unit_price,
                "Total_Price": total_price
            })
        except Exception:
            continue

    return result
extract_intermountain_invoice_robust.name = "Intermountain Wood Products 2"


def extract_invoice_intermountain2(pdf_path):
    doc = fitz.open(pdf_path)
    lines = "\n".join([page.get_text() for page in doc]).splitlines()

    # Optional: stop scanning before totals
    stop_idx = next((i for i, line in enumerate(lines) if "Please Pay This" in line), len(lines))
    working_lines = lines[:stop_idx]

    item_blocks = []
    i = 0
    while i < len(working_lines):
        # Detect start of item: e.g., "10 EA", "35 BF", "1 PC", etc.
        if re.match(r"^\d+\s+\w+$", working_lines[i].strip()):
            block = [working_lines[i].strip()]
            j = i + 1
            while j < len(working_lines) and not re.match(r"^\d+\s+\w+$", working_lines[j].strip()):
                block.append(working_lines[j].strip())
                j += 1
            item_blocks.append(block)
            i = j
        else:
            i += 1

    parsed_items = []
    for block in item_blocks:
        try:
            quantity_unit = block[0]
            item_code = ""
            unit_price = 0.0
            unit_type = ""
            amount = 0.0
            description_lines = []
            y_found = False

            for line in block[1:]:
                if re.fullmatch(r"[A-Z0-9\-]{3,}", line):  # Detect item code
                    item_code = line
                elif line.strip() == "Y":
                    y_found = True
                elif y_found and re.match(r"^\d+\.\d{2}$", line):  # Unit price
                    unit_price = float(line)
                elif unit_price and re.fullmatch(r"[A-Z]+", line):  # Unit type like MSF, MBF
                    unit_type = line
                elif unit_type and re.match(r"^\d+\.\d{4}$", line):  # Amount
                    amount = float(line)
                else:
                    if line.strip():
                        description_lines.append(line.strip())

            parsed_items.append({
                "Quantity & Unit": quantity_unit,
                "Description": " ".join(description_lines),
                "Item Code": item_code,
                "Unit Price": unit_price,
                "Unit Type": unit_type,
                "Amount": amount
            })
        except Exception as e:
            continue

    return pd.DataFrame(parsed_items)
extract_invoice_intermountain2.name = "Intermountain Wood Products 3"


def extract_line_items_from_hafele_invoice(pdf_path):
    # Extract tables using Camelot
    tables = camelot.read_pdf(pdf_path, pages='all', strip_text='\n', flavor='stream')  # try stream if lattice fails

    line_items = []
    current_po_number = None

    for table in tables:
        df = table.df

        # Loop through each row and find line items by pattern
        for idx, row in df.iterrows():
            row_text = ' '.join(row.dropna())

            # Check for PO Number
            po_match = re.match(r"PO Number: (\d+)", row_text)
            if po_match:
                current_po_number = po_match.group(1)
                continue

            # Detect line item by POS structure (e.g., "1 16 Piece ...")
            pos_match = re.match(r"^\d+\s+\d+\s+Piece", row_text)
            if pos_match:
                fields = row_text.split()
                try:
                    pos = fields[0]
                    quantity = fields[1]
                    unit = fields[2]
                    article_no = fields[3]
                    unit_price = fields[-2]
                    amount = fields[-1]
                    description = ' '.join(fields[4:-2])

                    line_items.append({
                        "PO Number": current_po_number,
                        "POS": pos,
                        "Quantity": quantity,
                        "Unit": unit,
                        "Article No.": article_no,
                        "Description": description,
                        "Unit Price (USD)": unit_price,
                        "Amount (USD)": amount
                    })
                except Exception as e:
                    print(f"Error parsing row: {row_text}")
                    continue

    return pd.DataFrame(line_items)




def extract_line_items_from_hafele_invoice_fallback(pdf_path):
    doc = fitz.open(pdf_path)
    lines = "\n".join([page.get_text() for page in doc]).splitlines()

    line_items = []
    current_po = None
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Detect PO Number
        if "PO Number:" in line:
            match = re.search(r"PO Number:\s*(\d+)", line)
            if match:
                current_po = match.group(1)
            i += 1
            continue

        # Match POS number (start of line item)
        if re.match(r"^\d{1,2}$", line):  # POS is usually 1–2 digits
            try:
                pos = lines[i].strip()
                qty = lines[i + 1].strip()
                unit = lines[i + 2].strip()
                article_no = lines[i + 3].strip()

                # Skip 'Pack Qty =' and '( 1 )'
                unit_price = lines[i + 6].strip()
                amount = lines[i + 7].strip()

                # Avoid false positives from headers
                if not re.match(r"^\d+(\.\d+)?$", unit_price) or not re.match(r"^\d+(\.\d+)?$", amount):
                    i += 1
                    continue

                # Capture multiline description until "HTS:" or empty line
                description_lines = []
                j = i + 8
                while j < len(lines):
                    desc_line = lines[j].strip()
                    if not desc_line or re.match(r"^HTS:", desc_line) or re.match(r"^\d{1,2}$", desc_line):
                        break
                    description_lines.append(desc_line)
                    j += 1

                line_items.append({
                    "PO Number": current_po,
                    "POS": pos,
                    "Quantity": qty,
                    "Unit": unit,
                    "Article No.": article_no,
                    "Unit Price (USD)": unit_price,
                    "Amount (USD)": amount,
                    "Description": " ".join(description_lines)
                })

                i = j  # Skip to next block
            except Exception:
                i += 1  # Skip malformed blocks
        else:
            i += 1

    return pd.DataFrame(line_items)


def extract_sierra_invoice_data(pdf_path):
    """
    Extracts structured invoice data from Sierra Forest Products PDFs.
    Supports multi-line line items and irregular layout structure.

    Returns:
        dict: {
            invoice_number,
            ship_date,
            vendor_name,
            invoice_total,
            invoice_due_date,
            invoice_amount,
            cust_po,
            line_items: [ {Id, Description, Qty, Unit, Total_Price}, ... ]
        }
    """
    doc = fitz.open(pdf_path)
    lines = "\n".join([page.get_text() for page in doc]).splitlines()

    result = {
        "invoice_number": None,
        "ship_date": None,
        "vendor_name": "Sierra Forest Products, Inc.",
        "invoice_total": None,
        "invoice_due_date": None,
        "invoice_amount": None,
        "cust_po": None,
        "line_items": []
    }

    # --- Extract header-level fields ---
    for i, line in enumerate(lines):
        if not result["invoice_number"]:
            match = re.search(r"Invoice[#\s]*([A-Z0-9-]+)", line)
            if match:
                result["invoice_number"] = match.group(1)

        if not result["ship_date"] and "Ship Date" in line:
            if i > 0:
                date_match = re.search(r"\d{2}/\d{2}/\d{4}", lines[i - 1])
                if date_match:
                    result["ship_date"] = date_match.group(0)

        if not result["invoice_due_date"] and "paid by" in line.lower():
            match = re.search(r"(\d{2}/\d{2}/\d{4})", line)
            if match:
                result["invoice_due_date"] = match.group(1)

        if not result["invoice_total"] and line.strip().upper() == "TOTAL":
            if i + 1 < len(lines):
                result["invoice_total"] = lines[i + 1].strip()

        if not result["invoice_amount"]:
            match = re.match(r"^\d{1,3}(,\d{3})*\.\d{2}$", line.strip())
            if match:
                amt = match.group(0).replace(",", "")
                if float(amt) > 100:  # Avoid zero or filler amounts
                    result["invoice_amount"] = amt

        if not result["cust_po"] and "Cust. P.O." in line:
            if i + 1 < len(lines):
                result["cust_po"] = lines[i + 1].strip()

    # --- Extract line items (10-line repeating blocks) ---
    i = 0
    while i < len(lines) - 9:
        if re.search(r'G2S PB', lines[i]):
            try:
                description = lines[i].strip()
                ext_price = lines[i + 2].strip().replace(",", "")
                qty = lines[i + 3].strip()
                unit_price = lines[i + 4].strip()
                item_code = lines[i + 8].strip()

                if re.match(r'^\d{5,}$', item_code):
                    result["line_items"].append({
                        "Id": item_code,
                        "Description": description,
                        "Qty": qty,
                        "Unit": unit_price,
                        "Total_Price": ext_price
                    })
                i += 10  # Skip ahead to next item
            except Exception:
                i += 1
        else:
            i += 1

    return result
extract_sierra_invoice_data.name = "Sierra Forest Products"
