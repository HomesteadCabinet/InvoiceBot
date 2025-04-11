from difflib import get_close_matches
import camelot
import json
import pandas as pd
import pdfplumber
import pymupdf as fitz
import re


# These parsers are AI generated. Dont judge me, just use the prompt template below to generate a new parser
# for a new vendor or to fix a failing invoice. Each invoice is different, so we need custom parsers.
# It helps to use multiple invoices from the same vendor to train the AI.


# You're an expert in Python and PDF parsing using `pdfplumber`, `PyMuPDF`, and `Camelot`.
# I need you to generate a custom parsing function for a vendors PDF invoices. I will provide:
# - One or more PDF invoices from the vendor
# - Key fields I need extracted
# - Notes about how the invoice is structured
# - I may provide a method I am working on that is failing and needs to be fixed.

# Please return a Python function that:
# - Accepts a `pdf_path` as input
# - Uses `pdfplumber`, `PyMuPDF`, `Camelot` or all of the above to extract structured data
# - Returns a `dict` or `DataFrame` with the extracted fields

# Do not attempt to use any hard coded values from line items for matching. Vendor Name field can be
# hard coded per function.
# Some fields are repeated across the document, so you will need to be careful to not duplicate them.
# Some fields have a header above the value.
# Methods need to be able to handle irregularly structured invoices.
# Methods need to be able to handle invoices with 1 or more line items, possibly with multiple pages.
# Returned key names need to be in snake_case
# Test the parser with each invoice you are given to ensure it works correctly.
# Line items are everything from header containing 'Code' to the next row containing 'Total'


# Each field has our column name and the text to match serparated by a colon.
# Methods need to return these fields along with the line items

# Key fields to extract:
# Fields that have the value on the cell immediately below the header
# - Invoice Number:Invoice No.
# - Ship Date:Ship Date
# - Date Ordered:Inv Date
# - Invoice Total:Total
# - Cust PO: Cust. P.O. #

# Inline or other Fields
# - Vendor Name: [Please attempt to extract the vendor name from the PDF]
# - Invoice Due Date: if paid by [value]

# Methods need to return a line items, each with the following fields:
# Line items:
# - Id:Code
# - Name: Description[0]
# - Description: Description[1:]
# - Qty:Ordered
# - Unit:
# - Unit_Price: Unit Price
# - Total_Price: Ext. Price



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
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    lines = text.splitlines()

    result = {
        "invoice_number": None,
        "ship_date": None,
        "date_ordered": None,
        "vendor_name": "Sierra Forest Products, Inc.",
        "invoice_total": None,
        "invoice_due_date": None,
        "cust_po": None,
        "line_items": []
    }

    # --- Extract Header-Level Fields ---
    for i, line in enumerate(lines):
        if not result["invoice_number"]:
            match = re.search(r"Invoice[#\s]*([A-Z0-9-]+)", line)
            if match:
                result["invoice_number"] = match.group(1)

        if not result["ship_date"] and "Ship Date" in line:
            date_matches = re.findall(r"\d{2}/\d{2}/\d{4}", line)
            if date_matches:
                result["ship_date"] = date_matches[0]

        if not result["date_ordered"] and "Order Date" in line:
            for offset in range(1, 3):
                if i + offset < len(lines):
                    match = re.search(r"\d{2}/\d{2}/\d{4}", lines[i + offset])
                    if match:
                        result["date_ordered"] = match.group(0)
                        break

        if not result["invoice_due_date"]:
            match = re.search(r"paid by\s+(\d{2}/\d{2}/\d{4})", line.lower())
            if match:
                result["invoice_due_date"] = match.group(1)

        if not result["cust_po"] and "Cust. P.O." in line:
            result["cust_po"] = lines[i + 1].strip() if i + 1 < len(lines) else None

        if not result["invoice_total"] and line.strip().upper() == "TOTAL":
            for j in range(i + 1, len(lines)):
                amt_match = re.search(r"\d{1,3}(?:,\d{3})*\.\d{2}", lines[j])
                if amt_match:
                    result["invoice_total"] = amt_match.group(0)
                    break

    # --- New Logic for Parsing Line Items ---
    for line in lines:
        # Try to extract values from lines with prices and item codes
        match = re.match(
            r'^(.+?)\s+(\d{1,3}(?:,\d{3})*\.\d{2})\s+(\d+)\s+(\d{1,3}(?:,\d{3})*\.\d{2})\s+\d+\s+/(\d+)$',
            line.strip()
        )
        if match:
            description, total_price, qty, unit_price, item_id = match.groups()
            result["line_items"].append({
                "Id": item_id,
                "Name": "Item",
                "Description": description.strip(),
                "Qty": qty,
                "Unit": "",  # Unit (e.g., "PC") is hard to isolate in this format
                "Unit_Price": unit_price,
                "Total_Price": total_price
            })

    return result

extract_sierra_invoice_data.name = "Sierra Forest Products"


def parse_vendor_invoice(pdf_path: str) -> dict:
    """
    Parse a vendor invoice PDF and return a dictionary with header fields and line items.

    Key header fields are assumed to have their value in the cell immediately below (or on the same line after)
    the header:
      - invoice_number: from "Invoice No." or "Invoice#"
      - ship_date: from "Ship Date" (expected as MM/DD/YYYY)
      - date_ordered: from "Inv Date" (expected as MM/DD/YYYY)
      - invoice_total: from "Total" (expected as a monetary value)
      - cust_po: from "Cust. P.O. #"

    Inline fields:
      - invoice_due_date: the date (MM/DD/YYYY) following "if paid by"
      - vendor_name: hard coded ("Sierra Forest Products, Inc.")

    Line items:
      Using Camelot hybrid mode (combining lattice and stream), the function processes tables whose header row
      contains the word "code". Rows are processed from row 1 (after the header) until a row is encountered
      where the first cell (after stripping) starts with "total". If a cell contains newline characters, it is split
      and separate line items are created by zipping the split values (using the first value as a fallback).

      For each line item, these snake_case fields are returned:
        - id           : from the column with header containing "code"
        - name         : the first line from the "description" cell (split by newline)
        - description  : additional text from the "description" cell (after the first line)
        - qty          : from the column whose header exactly matches "ordered" or "shipped"
        - unit_price   : from the column whose header contains "unit price"
        - total_price  : from the column whose header contains "ext" or "total price"
        - unit         : from the column whose header contains "unit" (excluding unit price)
    """
    # Helper: Clean an extracted header value.
    def clean_value(field, value):
        if not value:
            return None
        value = value.strip()
        if field in ['ship_date', 'date_ordered', 'invoice_due_date']:
            m = re.search(r'\d{1,2}/\d{1,2}/\d{4}', value)
            return m.group(0) if m else value.split()[0]
        elif field == 'invoice_number':
            m = re.search(r'L\d+', value)
            return m.group(0) if m else value.split()[0]
        elif field == 'invoice_total':
            m = re.search(r'[\d,]+\.\d{2}', value)
            return m.group(0) if m else value.split()[0]
        elif field == 'cust_po':
            # Return the first two tokens (for example "23700 Moyer")
            return " ".join(value.split()[:2])
        else:
            return value

    # Helper: Extract the cell value immediately following a header text.
    def extract_cell_value(lines, header_text):
        for i, line in enumerate(lines):
            if header_text.lower() in line.lower():
                parts = re.split(re.escape(header_text), line, flags=re.IGNORECASE)
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip()
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    if next_line:
                        return next_line
                    j += 1
        return None

    # Helper: Dynamically parse a Camelot table DataFrame into line items.
    def dynamic_line_item_parser(df):
        header_row = df.iloc[0].tolist()
        header_map = {}
        for idx, col in enumerate(header_row):
            col_lower = str(col).strip().lower()
            if "code" in col_lower:
                header_map["id"] = idx
            if "description" in col_lower:
                header_map["description"] = idx
            # Use regex with word boundaries for "ordered" or "shipped"
            if re.search(r'\bordered\b', col_lower) or re.search(r'\bshipped\b', col_lower):
                header_map["qty"] = idx
            if "unit price" in col_lower:
                header_map["unit_price"] = idx
            if (("ext" in col_lower) or ("total price" in col_lower)) and not col_lower.startswith("total"):
                header_map["total_price"] = idx
            if "unit" in col_lower and "price" not in col_lower:
                header_map["unit"] = idx

        line_items = []
        for i in range(1, len(df)):
            row = df.iloc[i].tolist()
            first_cell = str(row[0]).strip().lower()
            if first_cell.startswith("total"):
                break
            row_text = " ".join(str(cell) for cell in row if cell)
            if not re.search(r'\d', row_text):
                continue

            # For each field, split cell text by newline.
            item_fields = {}
            max_lines = 1
            for key, col_idx in header_map.items():
                cell_val = str(row[col_idx]).strip() if col_idx < len(row) else ""
                splits = [s.strip() for s in cell_val.split("\n") if s.strip()]
                item_fields[key] = splits
                if len(splits) > max_lines:
                    max_lines = len(splits)
            # Create one line item per sub-value index.
            for j in range(max_lines):
                item = {}
                for key in header_map.keys():
                    values = item_fields.get(key, [""])
                    item[key] = values[j] if j < len(values) else values[0]
                # For description, separate first line (used as name) from additional text.
                if "description" in item:
                    desc_parts = item["description"].split("\n")
                    if not item.get("name"):
                        item["name"] = desc_parts[0] if desc_parts else ""
                    item["description"] = " ".join(desc_parts[1:]) if len(desc_parts) > 1 else ""
                line_items.append(item)
        return line_items

    # --- Main Extraction ---
    full_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
    except Exception as e:
        print(f"Error reading PDF with pdfplumber: {e}")
    lines = full_text.splitlines()

    raw_invoice_number = extract_cell_value(lines, "Invoice No.")
    if not raw_invoice_number:
        raw_invoice_number = extract_cell_value(lines, "Invoice#")
    raw_ship_date = extract_cell_value(lines, "Ship Date")
    raw_date_ordered = extract_cell_value(lines, "Inv Date")
    raw_invoice_total = extract_cell_value(lines, "Total")
    raw_cust_po = extract_cell_value(lines, "Cust. P.O. #")

    invoice_number = clean_value("invoice_number", raw_invoice_number)
    ship_date = clean_value("ship_date", raw_ship_date)
    date_ordered = clean_value("date_ordered", raw_date_ordered)
    invoice_total = clean_value("invoice_total", raw_invoice_total)
    cust_po = clean_value("cust_po", raw_cust_po)

    invoice_due_date = None
    due_date_match = re.search(r'if paid by\s*(?:[\$\d.]+\s*)?(\d{1,2}/\d{1,2}/\d{4})', full_text, re.IGNORECASE)
    if due_date_match:
        invoice_due_date = clean_value("invoice_due_date", due_date_match.group(1))

    vendor_name = "Sierra Forest Products, Inc."

    try:
        tables_lattice = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
    except Exception as e:
        print(f"Error extracting tables in lattice mode with Camelot: {e}")
        tables_lattice = []
    try:
        tables_stream = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    except Exception as e:
        print(f"Error extracting tables in stream mode with Camelot: {e}")
        tables_stream = []
    combined_tables = list(tables_lattice) + list(tables_stream)
    line_items = []
    for table in combined_tables:
        header_row_text = " ".join(str(x) for x in table.df.iloc[0].tolist()).lower()
        if "code" in header_row_text:
            items = dynamic_line_item_parser(table.df)
            line_items.extend(items)

    parsed_invoice = {
        "invoice_number": invoice_number,
        "ship_date": ship_date,
        "date_ordered": date_ordered,
        "invoice_total": invoice_total,
        "cust_po": cust_po,
        "vendor_name": vendor_name,
        "invoice_due_date": invoice_due_date,
        "line_items": line_items
    }
    return parsed_invoice
