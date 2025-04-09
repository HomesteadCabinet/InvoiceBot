import camelot
import pandas as pd
import re
import pymupdf as fitz


def extract_invoice_intermountain2(pdf_path):
    doc = fitz.open(pdf_path)
    lines = "\n".join([page.get_text() for page in doc]).splitlines()

    # Stop at the summary section
    stop_idx = next((i for i, line in enumerate(lines) if "Invoice Total" in line), len(lines))
    working_lines = lines[:stop_idx]

    # Detect blocks starting with quantity/unit pattern like "35 BF"
    item_blocks = []
    i = 0
    while i < len(working_lines):
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

    # Parse each block
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
                if re.fullmatch(r"[A-Z0-9]{3,}", line):
                    item_code = line
                elif line == "Y":
                    y_found = True
                elif y_found and re.match(r"^\d+\.\d{2}$", line):
                    unit_price = float(line)
                elif unit_price and re.fullmatch(r"[A-Z]+", line):
                    unit_type = line
                elif unit_type and re.match(r"^\d+\.\d{4}$", line):
                    amount = float(line)
                else:
                    description_lines.append(line)

            parsed_items.append({
                "Quantity & Unit": quantity_unit,
                "Description": " ".join(description_lines),
                "Item Code": item_code,
                "Unit Price": unit_price,
                "Unit Type": unit_type,
                "Amount": amount
            })
        except Exception:
            continue

    return pd.DataFrame(parsed_items)




def extract_invoice_intermountain(pdf_path):
    # Extract tables using stream flavor for irregular structure
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream', strip_text='\n')

    # Combine all tables into one
    df_all = pd.concat([table.df for table in tables], ignore_index=True)

    # Flatten all columns into single line-based rows
    text_lines = df_all.apply(lambda row: ' '.join(row.dropna().astype(str)).strip(), axis=1).tolist()

    items = []
    i = 0

    while i < len(text_lines):
        if re.match(r"^\d+\s+\w+$", text_lines[i]):  # e.g. "15 BF"
            block = [text_lines[i]]
            j = i + 1
            while j < len(text_lines) and not re.match(r"^\d+\s+\w+$", text_lines[j]):
                block.append(text_lines[j])
                j += 1

            try:
                quantity_unit = block[0]
                y_idx = block.index("Y") if "Y" in block else -1
                unit_price = float(block[y_idx + 1]) if y_idx != -1 else 0.0
                unit_type = block[y_idx + 2] if y_idx != -1 and len(block) > y_idx + 2 else ""
                amount = float(block[y_idx + 3]) if y_idx != -1 and len(block) > y_idx + 3 else 0.0
                item_code = block[y_idx - 1] if y_idx > 0 else ""
                description = " ".join(block[1:y_idx - 1]) if y_idx > 1 else ""

                items.append({
                    "Quantity & Unit": quantity_unit,
                    "Description": description,
                    "Item Code": item_code,
                    "Unit Price": unit_price,
                    "Unit Type": unit_type,
                    "Amount": amount
                })
            except Exception:
                pass

            i = j
        else:
            i += 1

    return pd.DataFrame(items)




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


import fitz  # PyMuPDF
import re

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



d = extract_sierra_invoice_data('se1.pdf')
print(type(d))
print(d)
# print(d.tail())
