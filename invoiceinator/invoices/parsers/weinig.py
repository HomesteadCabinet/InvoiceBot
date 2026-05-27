"""Weinig Holz-Her / Weinig USA invoice and statement parser."""

from __future__ import annotations

import re

import pymupdf as fitz

from .schema import empty_invoice, invoice_bundle, make_line_item, normalize_invoice, to_float

_VENDOR_NAME = "Weinig Holz-Her USA, Inc."
_INVOICE_NUMBER_RE = re.compile(r"^(\d+)\s+RI$")
_MONEY_RE = re.compile(r"^-?(?:[\d,]+(?:\.\d{2,4})?|\.\d{2,4})$")
_MONEY_4_RE = re.compile(r"^-?(?:[\d,]+(?:\.\d{4})?|\.\d{4})$")
_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")
_DESC_RE = re.compile(r"^(.+?)\s{2,}(.+?)\s{2,}(EA|PK|PC|EA\.)$", re.IGNORECASE)
_DESC_SIMPLE_RE = re.compile(r"^(.+?)\s{2,}(EA|PK|PC|EA\.)$", re.IGNORECASE)
_STATEMENT_ROW_RE = re.compile(
    r"^(?:RI|USD)\s+(\d+)\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})\s+\.00\s+\.00$"
)


def _pages(pdf_path):
    doc = fitz.open(pdf_path)
    try:
        return [
            [line.strip() for line in page.get_text().splitlines() if line.strip()]
            for page in doc
        ]
    finally:
        doc.close()


def _is_statement(pages):
    return any("STATEMENT OF ACCOUNT" in line for page in pages for line in page)


def _vendor_name_from_pages(pages):
    for page in pages:
        for line in page:
            if line in {"Weinig Holz-Her USA, Inc.", "WEINIG USA, Inc."}:
                return line
    return _VENDOR_NAME


def _first_value_after(lines, label):
    for i, line in enumerate(lines):
        if line == label and i + 1 < len(lines):
            return lines[i + 1].strip()
    return None


def _extract_invoice_number(lines):
    for line in lines:
        m = _INVOICE_NUMBER_RE.match(line)
        if m:
            return m.group(1)
    return None


def _extract_invoice_date(lines):
    if "INVOICE" in lines:
        idx = lines.index("INVOICE")
        for candidate in lines[idx + 1 : idx + 5]:
            m = _DATE_RE.search(candidate)
            if m:
                return m.group(0)
    return _first_value_after(lines, "Invoice Date:")


def _extract_customer_number(lines):
    if "INVOICE" in lines:
        idx = lines.index("INVOICE")
        for candidate in lines[idx + 1 : idx + 6]:
            if re.fullmatch(r"\d+", candidate):
                return candidate
    return None


def _extract_customer_po(lines):
    if "INVOICE" in lines:
        idx = lines.index("INVOICE")
        candidates = lines[idx + 1 : idx + 7]
        for candidate in candidates:
            if re.fullmatch(r"\d+\s+(?:SP|RI)", candidate):
                continue
        if len(candidates) >= 5:
            return candidates[4]
    return None


def _extract_due_date(lines):
    for line in lines:
        m = re.search(r"Due Date:\s*(\d{1,2}/\d{1,2}/\d{2,4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_invoice_total(lines):
    net_idx = None
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].startswith("Net 30 Days"):
            net_idx = idx
            break
    if net_idx is None:
        return None

    money_values = []
    for idx in range(net_idx + 1, len(lines)):
        line = lines[idx].replace(",", "").strip()
        if _DATE_RE.fullmatch(line):
            break
        if _MONEY_RE.match(line):
            money_values.append(line)
    if money_values:
        return money_values[-1]
    return None


def _split_item_line(line):
    parts = [part.strip() for part in re.split(r"\s{2,}", line.strip()) if part.strip()]
    if len(parts) >= 3:
        desc = parts[0].rstrip("+").strip()
        item_id_candidates = [part for part in parts[1:-1] if part != "+"]
        item_id = item_id_candidates[0] if item_id_candidates else parts[1]
        unit = parts[-1]
        return desc, item_id, unit
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return line.strip(), "", "EA"


def _collect_descriptions(lines):
    descs = []
    in_items = False
    for line in lines:
        if line.startswith("MACHINE:") or line.endswith("Shipping Dock"):
            in_items = True
            continue
        if not in_items:
            continue
        if line.startswith("PLEASE NOTE COLUMN LABELED"):
            break
        if line.startswith("Per   "):
            continue
        if _DESC_RE.match(line) or _DESC_SIMPLE_RE.match(line):
            descs.append(line)
    return descs


def _collect_numeric_run(lines):
    values = []
    in_items = False
    for line in lines:
        if line.startswith("FOB Mooresville Shipping Dock"):
            in_items = True
            continue
        if not in_items:
            continue
        if _DESC_RE.match(line) or _DESC_SIMPLE_RE.match(line):
            break
        if line.startswith("Per   "):
            continue
        cleaned = line.replace(",", "").strip()
        if _MONEY_RE.match(cleaned) or _MONEY_4_RE.match(cleaned):
            values.append(cleaned)
    return values


def _parse_invoice_page(lines):
    invoice_number = _extract_invoice_number(lines)
    if not invoice_number:
        return None

    descs = _collect_descriptions(lines)
    numeric_values = _collect_numeric_run(lines)
    if len(numeric_values) < len(descs) * 2:
        return None

    prices = numeric_values[: len(descs)]
    quantities = numeric_values[len(descs) : len(descs) * 2]

    invoice = empty_invoice(_VENDOR_NAME)
    invoice["invoice_number"] = invoice_number
    invoice["date_ordered"] = _extract_invoice_date(lines)
    invoice["ship_date"] = _extract_invoice_date(lines)
    invoice["cust_po"] = _extract_customer_po(lines) or _extract_customer_number(lines)
    invoice["invoice_due_date"] = _extract_due_date(lines)
    invoice["invoice_total"] = _extract_invoice_total(lines)

    for desc_line, price, qty in zip(descs, prices, quantities):
        desc, item_id, unit = _split_item_line(desc_line)
        qty_value = to_float(qty)
        unit_price = to_float(price)
        invoice["line_items"].append(
            make_line_item(
                item_id=item_id or desc,
                name=desc,
                description=item_id if item_id and item_id != desc else "",
                qty=str(qty_value).rstrip("0").rstrip(".") if qty_value % 1 else str(int(qty_value)),
                unit=unit or "EA",
                unit_price=unit_price,
                total_price=unit_price * qty_value,
            )
        )

    return normalize_invoice(invoice)


def _parse_statement(pages):
    invoices = []
    seen = set()
    for page in pages:
        for line in page:
            normalized = re.sub(r"\s+", " ", line.strip())
            m = _STATEMENT_ROW_RE.match(normalized)
            if not m:
                continue
            invoice_number, inv_date, desc, amount = m.groups()
            if invoice_number in seen:
                continue
            seen.add(invoice_number)
            invoice = empty_invoice(_VENDOR_NAME)
            invoice["invoice_number"] = invoice_number
            invoice["date_ordered"] = inv_date
            invoice["ship_date"] = inv_date
            invoice["cust_po"] = desc.strip()
            invoice["invoice_total"] = amount.replace(",", "")
            invoice["line_items"].append(
                make_line_item(
                    item_id=invoice_number,
                    name=desc.strip(),
                    description="Statement open invoice",
                    qty="1",
                    unit_price=to_float(amount),
                    total_price=to_float(amount),
                )
            )
            invoices.append(normalize_invoice(invoice))
    return invoice_bundle(_VENDOR_NAME, invoices)


def parse_weinig_invoice(pdf_path):
    """Weinig invoice and statement parser."""
    pages = _pages(pdf_path)
    if _is_statement(pages):
        return _parse_statement(pages)

    grouped = []
    current = None
    for page in pages:
        parsed = _parse_invoice_page(page)
        if not parsed:
            continue
        invoice_number = parsed["invoice_number"]
        if current and current["invoice_number"] == invoice_number:
            current["pages"].append(parsed)
        else:
            current = {"invoice_number": invoice_number, "pages": [parsed]}
            grouped.append(current)

    invoices = []
    vendor_name = _vendor_name_from_pages(pages)
    for group in grouped:
        merged = empty_invoice(vendor_name)
        merged["invoice_number"] = group["invoice_number"]
        for page_invoice in group["pages"]:
            for field in ("date_ordered", "ship_date", "invoice_due_date", "cust_po", "invoice_total"):
                if not merged.get(field) and page_invoice.get(field):
                    merged[field] = page_invoice[field]
            merged["line_items"].extend(page_invoice.get("line_items") or [])
        invoices.append(normalize_invoice(merged))

    return invoice_bundle(vendor_name, invoices)


parse_weinig_invoice.name = _VENDOR_NAME
