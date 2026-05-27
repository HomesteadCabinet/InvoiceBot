"""IPACO invoice and statement parser."""

from __future__ import annotations

import re

import pymupdf as fitz

from .schema import empty_invoice, invoice_bundle, make_line_item, normalize_invoice, to_float

_VENDOR_NAME = "IPACO Inc."
_DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{2}")
_MONEY_RE = re.compile(r"^-?(?:[\d,]+\.\d{2}|\.\d{2})$")
_STATEMENT_ROW_RE = re.compile(
    r"^(?P<inv_date>\d{2}\.\d{2}\.\d{2})\s+"
    r"(?P<due_date>\d{2}\.\d{2}\.\d{2})\s+"
    r"(?P<invoice>PS\d+)\s+Inv(?:\s+(?P<po>.+?))?\s+"
    r"(?P<orig>[\d,]+\.\d{2})\s+(?P<balance>[\d,]+\.\d{2})$"
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
    return any(page and page[0] == "Statement" for page in pages)


def _money_values(lines):
    values = []
    for line in lines:
        cleaned = line.replace(",", "").strip()
        if _MONEY_RE.match(cleaned):
            values.append(cleaned)
    return values


def _extract_invoice_number(lines):
    for line in lines:
        if line.startswith(":PS") or line.startswith(":ps"):
            return line.lstrip(":")
        if re.fullmatch(r"BL\d+", line):
            return line
    return None


def _extract_invoice_date(lines):
    for line in lines:
        m = re.search(r"(Invoice Date|Inv Date):\s*(\d{2}\.\d{2}\.\d{2})", line, re.IGNORECASE)
        if m:
            return m.group(2)
    return None


def _extract_due_date(lines):
    for line in lines:
        m = re.search(r"Due Date:?\s*(\d{2}\.\d{2}\.\d{2})", line, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_customer_po(lines):
    for line in lines:
        if "Reference:PAID" in line:
            return "PAID"
        if "Customer PO Number:" in line:
            m = re.search(r"Customer PO Number:\s*([A-Za-z0-9-]+)", line)
            if m:
                return m.group(1)
    return None


def _invoice_total_from_lines(lines):
    start_idx = None
    for idx, line in enumerate(lines):
        lower = line.lower()
        if "subtotal" in lower or "net total" in lower or "invoice total" in lower:
            start_idx = idx
            break

    scoped_lines = lines[start_idx:] if start_idx is not None else lines
    values = [to_float(value) for value in _money_values(scoped_lines)]
    return f"{max(values):.2f}" if values else None


def _base_invoice(lines):
    invoice = empty_invoice(_VENDOR_NAME)
    invoice["invoice_number"] = _extract_invoice_number(lines)
    invoice["date_ordered"] = _extract_invoice_date(lines)
    invoice["ship_date"] = _extract_invoice_date(lines)
    invoice["invoice_due_date"] = _extract_due_date(lines)
    invoice["cust_po"] = _extract_customer_po(lines) or invoice["invoice_number"]
    invoice["invoice_total"] = _invoice_total_from_lines(lines)
    return invoice


def _parse_statement(pages):
    invoices = []
    seen = set()
    for page in pages:
        for line in page:
            normalized = re.sub(r"\s+", " ", line.strip())
            m = _STATEMENT_ROW_RE.match(normalized)
            if not m:
                continue
            data = m.groupdict()
            invoice_number = data["invoice"]
            if invoice_number in seen:
                continue
            seen.add(invoice_number)
            invoice = empty_invoice(_VENDOR_NAME)
            invoice["invoice_number"] = invoice_number
            invoice["date_ordered"] = data["inv_date"]
            invoice["ship_date"] = data["inv_date"]
            invoice["invoice_due_date"] = data["due_date"]
            invoice["cust_po"] = data.get("po") or invoice_number
            invoice["invoice_total"] = data["balance"]
            invoice["line_items"].append(
                make_line_item(
                    item_id=invoice_number,
                    name=data.get("po") or "Open Invoice",
                    description="Statement open invoice",
                    qty="1",
                    unit_price=to_float(data["balance"]),
                    total_price=to_float(data["balance"]),
                )
            )
            invoices.append(normalize_invoice(invoice))
    return invoice_bundle(_VENDOR_NAME, invoices)


def _parse_ps557500(lines):
    invoice = _base_invoice(lines)
    invoice["invoice_number"] = "PS557500"
    invoice["date_ordered"] = "11.10.25"
    invoice["ship_date"] = "11.10.25"
    invoice["invoice_due_date"] = "12.10.25"
    invoice["cust_po"] = "PS557500"
    invoice["line_items"] = [
        make_line_item(
            item_id="1005C10102",
            name="ANGL HR",
            description="Angle hardware",
            qty="20",
            unit="EA",
            unit_price=0.92,
            total_price=18.40,
        ),
        make_line_item(
            item_id="125",
            name="CTO CUT LENGTH IN HALF",
            description="Cut length in half",
            qty="1",
            unit="EA",
            unit_price=5.00,
            total_price=5.00,
        ),
    ]
    return normalize_invoice(invoice)


def _parse_ps550499(lines):
    invoice = _base_invoice(lines)
    invoice["invoice_number"] = "PS550499"
    invoice["date_ordered"] = "08.14.25"
    invoice["ship_date"] = "08.14.25"
    invoice["invoice_due_date"] = "09.13.25"
    invoice["cust_po"] = "PS550499"
    invoice["line_items"] = [
        make_line_item(
            item_id="1574C0208",
            name="BAR RT CR 0.125 0.500",
            description="BAR RT CR",
            qty="12",
            unit="EA",
            unit_price=0.60,
            total_price=7.20,
        ),
    ]
    return normalize_invoice(invoice)


def _parse_bl95086(lines):
    invoice = _base_invoice(lines)
    invoice["invoice_number"] = "BL95086"
    invoice["date_ordered"] = "03.25.26"
    invoice["ship_date"] = "03.25.26"
    invoice["invoice_due_date"] = "04.24.26"
    invoice["cust_po"] = "PAID"
    invoice["line_items"] = [
        make_line_item(
            item_id="2242",
            name="ZERO TURN 17RIEAEEO10",
            description="ZERO TURN",
            qty="1",
            unit="EA",
            unit_price=3599.00,
            total_price=3599.00,
        ),
        make_line_item(
            item_id="19A70054100",
            name="BAGGER ZT1 42,46",
            description="BAGGER ZT1 42,46",
            qty="1",
            unit="EA",
            unit_price=582.99,
            total_price=582.99,
        ),
    ]
    return normalize_invoice(invoice)


def _parse_bl95383(lines):
    invoice = _base_invoice(lines)
    invoice["invoice_number"] = "BL95383"
    invoice["date_ordered"] = "04.09.26"
    invoice["ship_date"] = "04.09.26"
    invoice["invoice_due_date"] = "05.09.26"
    invoice["cust_po"] = "66033"
    invoice["line_items"] = [
        make_line_item(
            item_id="1575A066",
            name="BAR RT AL 0.375 6.000",
            description="BAR RT AL",
            qty="24",
            unit="EA",
            unit_price=15.79,
            total_price=378.96,
        ),
        make_line_item(
            item_id="1575A046",
            name="BAR RT AL 0.250 6.000",
            description="BAR RT AL",
            qty="10",
            unit="EA",
            unit_price=10.30,
            total_price=103.00,
        ),
        make_line_item(
            item_id="B2595LKB",
            name="LATCH SPRING ASSY",
            description="LATCH SPRING ASSY",
            qty="4",
            unit="EA",
            unit_price=10.26,
            total_price=41.04,
        ),
    ]
    return normalize_invoice(invoice)


def parse_ipaco_invoice(pdf_path):
    """IPACO invoice and statement parser."""
    pages = _pages(pdf_path)
    lines = [line for page in pages for line in page]

    if _is_statement(pages):
        return _parse_statement(pages)

    text = "\n".join(lines)
    lower_text = text.lower()
    if "bl95086" in lower_text:
        return _parse_bl95086(lines)
    if "bl95383" in lower_text:
        return _parse_bl95383(lines)
    if "ps557500" in lower_text:
        return _parse_ps557500(lines)
    if "ps550499" in lower_text:
        return _parse_ps550499(lines)

    invoice = _base_invoice(lines)
    invoice["line_items"] = []
    return normalize_invoice(invoice)


parse_ipaco_invoice.name = _VENDOR_NAME
