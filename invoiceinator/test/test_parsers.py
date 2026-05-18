#!/usr/bin/env python
"""Run all invoice parsers against test PDFs and print a summary."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pymupdf as fitz

from invoices import parsers
from invoices.parsers.pdf import pdf_text
from invoices.parsers import wurth as wurth_parser

_EB_INVOICE_RE = re.compile(r"^\d{10}-\d{3}$")
_EB_ITEM_ID_RE = re.compile(r"^(?:P\d*|JW)-[\w-]+$", re.I)

# Map each test PDF to the parser that should handle it
PDF_PARSER_MAP = {
    "bitdefender.pdf": "parse_bitdefender_invoice",
    "crexendo.pdf": "parse_crexendo_invoice",
    "generic.pdf": "parse_american_saw_invoice",
    "hafele_test1.pdf": "parse_hafele_invoice",
    "hm1.pdf": "parse_high_mountain_invoice",
    "hm2.pdf": "parse_high_mountain_invoice",
    "industrial_tool_supply.pdf": "parse_industrial_tool_supply_invoice",
    "im2.pdf": "parse_intermountain_invoice",
    "im3.pdf": "parse_intermountain_invoice",
    "se1.pdf": "parse_sierra_invoice",
    "se2.pdf": "parse_sierra_invoice",
    "se3.pdf": "parse_sierra_invoice",
    "sierra.pdf": "parse_sierra_invoice",
    "wi-fiber.pdf": "parse_wi_fiber_invoice",
}

EDGEBANDING_EXPECTED = {
    "eb1.pdf": {
        "invoice_number": "0001801016-001",
        "invoice_total": "72.90",
        "cust_po": "26020 Bryan",
        "date_ordered": "05/13/26",
        "ship_date": "05/13/26",
        "item_id": "P1-3248TFA-24",
        "qty": "300",
        "unit_price": 0.243,
        "name_contains": "Opto Printatre",
    },
    "eb2.pdf": {
        "invoice_number": "0001799235-001",
        "invoice_total": "60.90",
        "cust_po": "26779 Pittard Barn",
        "date_ordered": "05/07/26",
        "ship_date": "05/07/26",
        "item_id": "P1-20215MMTF-24",
        "qty": "300",
        "unit_price": 0.203,
        "name_contains": "Black Velvet",
    },
    "eb3.pdf": {
        "invoice_number": "0001793413-001",
        "invoice_total": "72.90",
        "cust_po": "26195 Fennell Rose B1",
        "date_ordered": "04/17/26",
        "ship_date": "04/28/26",
        "item_id": "P1-2021TF-24",
        "qty": "300",
        "unit_price": 0.243,
        "name_contains": "Pearl",
    },
    "eb4.pdf": {
        "invoice_number": "0001797916-001",
        "invoice_total": "142.20",
        "cust_po": "26719 Pontikes",
        "date_ordered": "05/04/26",
        "ship_date": "05/04/26",
        "item_count": 2,
        "items": {
            "P-3298TF-24": {
                "qty": "600",
                "total_price": 54.00,
                "name_contains": "Valley Pecan",
            },
            "P1-8673F-24": {
                "qty": "300",
                "total_price": 88.20,
                "name_contains": "Nepal Teak",
            },
        },
    },
    "eb5.pdf": {
        "invoice_number": "0001796259-001",
        "invoice_total": "916.00",
        "cust_po": "Shop 4/28/26",
        "date_ordered": "04/28/26",
        "ship_date": "04/28/26",
        "item_id": "JW-608-00-PUR",
        "qty": "4",
        "unit_price": 229.00,
        "name_contains": "Granular",
    },
}

WURTH_INVOICE_COUNTS = {
    "wurth.pdf": 4,
    "wurth2.pdf": 1,
    "wurth3.pdf": 4,
    "wurth4.pdf": 4,
    "wurth5.pdf": 2,
    "wurth6.pdf": 4,
}

WURTH_EXPECTED = {
    "wurth.pdf": {
        "invoice_number": "9026368059",
        "invoice_total": "51.38",
        "subtotal": 40.99,
        "item_count": 2,
        "part_ids": {"B956A1006", "B71B758D"},
    },
    "wurth2.pdf": {
        "invoice_number": "9026384419",
        "invoice_total": "26.09",
        "subtotal": 15.70,
        "item_count": 1,
        "part_ids": {"PRO600-FCLIPNARROW"},
    },
    "wurth3.pdf": {
        "invoice_number": "9026368059",
        "invoice_total": "51.38",
        "subtotal": 40.99,
        "item_count": 2,
        "part_ids": {"B956A1006", "B71B758D"},
    },
    "wurth4.pdf": {
        "invoice_number": "9026363913",
        "invoice_total": "467.6",
        "subtotal": 467.60,
        "item_count": 2,
        "part_ids": {"CHC109-4725-1"},
    },
}

# Every Allmoxy-export test PDF uses the same parser
_test_dir = os.path.dirname(os.path.abspath(__file__))
for _pdf in sorted(os.listdir(_test_dir)):
    if _pdf.startswith("allmoxy") and _pdf.endswith(".pdf"):
        PDF_PARSER_MAP[_pdf] = "parse_allmoxy_invoice"
    if _pdf.startswith("wurth") and _pdf.endswith(".pdf"):
        PDF_PARSER_MAP[_pdf] = "parse_wurth_invoice"
    if _pdf.startswith("eb") and _pdf.endswith(".pdf"):
        PDF_PARSER_MAP[_pdf] = "parse_edgebanding_services_invoice"

# Seller name between Invoice # and Bill To (when present in the PDF)
ALLMOXY_EXPECTED_VENDOR = {
    "allmoxy2.pdf": "Lewis Cabinet Specialties Group LLC",
    "allmoxy3.pdf": "Lewis Cabinet Specialties Group LLC",
    "allmoxy335.pdf": "Salt City Mill",
}

# Door table continues after page footer in PDF text order (items 2.03–2.09)
ALLMOXY_EXPECTED_ITEM_IDS = {
    "allmoxy_bw.pdf": {
        "1 01",
        "2 01", "2 02", "2 03", "2 04", "2 05", "2 06", "2 07", "2 08", "2 09",
        "3 01", "3 02", "3 03", "3 04", "3 05", "3 06",
        "4 01",
    },
}

REQUIRED_PARSER_OUTPUT_KEYS = {"vendor_name", "invoices"}
REQUIRED_INVOICE_KEYS = {
    "invoice_number",
    "ship_date",
    "date_ordered",
    "vendor_name",
    "invoice_total",
    "invoice_due_date",
    "cust_po",
    "line_items",
}
REQUIRED_LINE_ITEM_KEYS = {
    "id",
    "name",
    "description",
    "qty",
    "unit",
    "unit_price",
    "total_price",
    "width",
    "length",
    "height",
}


def _validate_wurth_result(result, pdf_name=None):
    """Generic checks for any Wurth invoice parse (first page of PDF)."""
    if result.get("vendor_name") != "Wurth Louis and Company":
        raise AssertionError(f"vendor_name {result.get('vendor_name')!r}")
    if not result.get("invoice_number"):
        raise AssertionError("expected invoice_number")
    if not result["line_items"]:
        raise AssertionError("expected at least one line item")
    line_sum = sum(float(item["total_price"]) for item in result["line_items"])
    inv_total = float(result.get("invoice_total") or 0)
    if inv_total == 0 and line_sum != 0:
        raise AssertionError("invoice_total missing but line items have amounts")
    if inv_total != 0 and abs(line_sum) > abs(inv_total) + 0.02:
        raise AssertionError(
            f"line item total {line_sum:.2f} exceeds invoice total {inv_total:.2f}"
        )


def _validate_wurth_page(lines, result):
    """Validate a single Wurth page (used for multi-invoice PDFs)."""
    _validate_wurth_result(result)
    line_sum = sum(float(item["total_price"]) for item in result["line_items"])
    subtotal, energy_fee, total = wurth_parser._wurth_totals_from_lines(lines)
    if total is not None and abs(float(result.get("invoice_total") or 0) - total) > 0.02:
        raise AssertionError(
            f"invoice_total {result.get('invoice_total')} != parsed total {total}"
        )
    if subtotal is not None and abs(line_sum - subtotal) > 0.02:
        # Credit memos may apply extra fees so |line_sum| <= |subtotal|
        if subtotal < 0 and abs(line_sum) <= abs(subtotal) + 0.02:
            pass
        else:
            raise AssertionError(f"line_sum {line_sum:.2f} != subtotal {subtotal:.2f}")
    if subtotal is not None and energy_fee is not None and total is not None:
        if abs(subtotal + energy_fee - total) > 0.02:
            raise AssertionError(
                f"subtotal {subtotal:.2f} + energy {energy_fee:.2f} != total {total:.2f}"
            )
    elif total is not None and energy_fee is None and abs(line_sum - total) > 0.02:
        if subtotal is not None and abs(line_sum - subtotal) <= 0.02:
            pass
        elif total < 0 and abs(line_sum) <= abs(total) + 0.02:
            pass
        else:
            raise AssertionError(f"line_sum {line_sum:.2f} != total {total:.2f}")


def _wurth_invoices_from_raw(raw):
    if isinstance(raw, dict) and "invoices" in raw:
        return raw["invoices"]
    return [raw]


# Spot-check line descriptions that were mis-aligned before column-order fix.
WURTH_LINE_DESCRIPTIONS = {
    "9026368059": {
        "B956A1006": 'TIP-ON LRG DOORS 10"+ WIDE +4MM/-1M',
        "B71B758D": "CLIPTOP 125 0 PROT THK FO SFT CLS D",
    },
    "9026368060": {
        "CHC109-4725-1": "SELVA# PRO ACRILICO PGMNTD TC LOW G",
        "CHC876-9102-5": "SELVA# PRO ACRILICO PU HARDENER 5G",
        "MH2090-3/4": '3M 2090 PAINTERS BLUE TAPE 3/4" X 6',
    },
    "9026368061": {
        "B70T3553": "CLIPTOP BLMTN 86 DG RESTRICTION CLI",
        "RVLD-597-18CR": '18" LD CHROME TRAY DIVIDER 1 PER',
    },
}


def validate_wurth_bundle(raw, pdf_name=None):
    """Validate multi-invoice Wurth parser output."""
    invoices = _wurth_invoices_from_raw(raw)
    expected_count = WURTH_INVOICE_COUNTS.get(pdf_name)
    if expected_count is not None and len(invoices) != expected_count:
        raise AssertionError(
            f"expected {expected_count} invoices, got {len(invoices)}"
        )
    for invoice in invoices:
        _validate_wurth_result(invoice, pdf_name=pdf_name)
        expected_lines = WURTH_LINE_DESCRIPTIONS.get(invoice.get("invoice_number"))
        if expected_lines:
            by_id = {item["id"]: item for item in invoice["line_items"]}
            for part_id, desc in expected_lines.items():
                item = by_id.get(part_id)
                if not item:
                    raise AssertionError(f"missing part {part_id!r}")
                if item.get("name") != desc:
                    raise AssertionError(
                        f"{part_id} name {item.get('name')!r} != {desc!r}"
                    )
    expected_wurth = WURTH_EXPECTED.get(pdf_name)
    if expected_wurth and invoices:
        first = invoices[0]
        if first.get("invoice_number") != expected_wurth["invoice_number"]:
            raise AssertionError(
                f"first invoice_number {first.get('invoice_number')!r} != "
                f"{expected_wurth['invoice_number']!r}"
            )


def validate_wurth_all_pages(pdf_path):
    """Every page in a Wurth PDF must parse as a valid invoice."""
    pdf_name = os.path.basename(pdf_path)
    raw = wurth_parser.parse_wurth_invoice(pdf_path)
    validate_wurth_bundle(raw, pdf_name=pdf_name)
    doc = fitz.open(pdf_path)
    for page_index in range(len(doc)):
        lines = wurth_parser._wurth_page_lines(pdf_path, page_index)
        if not wurth_parser._wurth_page_is_invoice(lines):
            continue
        result = wurth_parser.parse_wurth_page(lines, pdf_path, page_index)
        _validate_wurth_page(lines, result)


def _validate_single_invoice(invoice):
    missing = REQUIRED_INVOICE_KEYS - set(invoice.keys())
    if missing:
        raise AssertionError(f"missing invoice keys: {missing}")
    if not isinstance(invoice["line_items"], list):
        raise AssertionError("line_items must be a list")
    for item in invoice["line_items"]:
        missing_item = REQUIRED_LINE_ITEM_KEYS - set(item.keys())
        if missing_item:
            raise AssertionError(f"line item missing keys: {missing_item}")


def _eb_pdfs_in_test_dir(test_dir):
    return {
        name
        for name in os.listdir(test_dir)
        if name.startswith("eb") and name.endswith(".pdf")
    }


def _check_eb_test_coverage(test_dir):
    missing = sorted(_eb_pdfs_in_test_dir(test_dir) - set(EDGEBANDING_EXPECTED))
    if missing:
        raise AssertionError(
            "add EDGEBANDING_EXPECTED entries for: " + ", ".join(missing)
        )


def _validate_edgebanding_result(invoice, pdf_path=None):
    """Generic checks for any Edgebanding Services invoice."""
    if invoice.get("vendor_name") != "Edgebanding Services":
        raise AssertionError(
            f"vendor_name {invoice.get('vendor_name')!r} != 'Edgebanding Services'"
        )
    invoice_number = invoice.get("invoice_number")
    if not invoice_number:
        raise AssertionError("expected invoice_number")
    if not _EB_INVOICE_RE.match(invoice_number):
        raise AssertionError(f"invoice_number format invalid: {invoice_number!r}")
    if not invoice.get("cust_po"):
        raise AssertionError("expected cust_po (job)")
    if not invoice.get("date_ordered") or not invoice.get("ship_date"):
        raise AssertionError("expected date_ordered and ship_date")

    items = invoice["line_items"]
    if not items:
        raise AssertionError("expected at least one line item")

    line_sum = 0.0
    for item in items:
        item_id = item.get("id") or ""
        if not _EB_ITEM_ID_RE.match(item_id):
            raise AssertionError(f"unexpected line item id {item_id!r}")
        qty = float(item["qty"])
        unit_price = float(item["unit_price"])
        total_price = float(item["total_price"])
        line_sum += total_price
        if qty > 0 and unit_price > 0 and abs(qty * unit_price - total_price) > 0.05:
            raise AssertionError(
                f"{item_id}: qty*unit_price {qty * unit_price:.2f} != total {total_price:.2f}"
            )
        if not (item.get("name") or "").strip():
            raise AssertionError(f"{item_id}: missing name")

    inv_total = float(invoice.get("invoice_total") or 0)
    if inv_total <= 0:
        raise AssertionError("expected positive invoice_total")
    if abs(line_sum - inv_total) > 0.02:
        raise AssertionError(
            f"line item total {line_sum:.2f} != invoice_total {inv_total:.2f}"
        )

    if pdf_path:
        text = pdf_text(pdf_path)
        subtotal_match = re.search(r"Subtotal\s*\n\s*([\d,]+\.\d{2})", text)
        if subtotal_match:
            subtotal = float(subtotal_match.group(1).replace(",", ""))
            if abs(subtotal - inv_total) > 0.02:
                raise AssertionError(
                    f"invoice_total {inv_total:.2f} != PDF subtotal {subtotal:.2f}"
                )


def validate_result(result, pdf_name=None, pdf_path=None):
    """Validate normalized parser output ``{vendor_name, invoices}``."""
    missing = REQUIRED_PARSER_OUTPUT_KEYS - set(result.keys())
    if missing:
        raise AssertionError(f"missing parser output keys: {missing}")
    if not isinstance(result["invoices"], list):
        raise AssertionError("invoices must be a list")
    if not result["invoices"]:
        raise AssertionError("invoices must not be empty")

    for invoice in result["invoices"]:
        _validate_single_invoice(invoice)

    if pdf_name and pdf_name.startswith("wurth"):
        validate_wurth_bundle(result, pdf_name=pdf_name)
        return

    if len(result["invoices"]) != 1:
        raise AssertionError(
            f"expected 1 invoice, got {len(result['invoices'])}"
        )

    invoice = result["invoices"][0]

    if pdf_name and pdf_name.startswith("allmoxy"):
        if not invoice["line_items"]:
            raise AssertionError("expected at least one line item")
        if not invoice.get("invoice_number"):
            raise AssertionError("expected invoice_number")
        expected_vendor = ALLMOXY_EXPECTED_VENDOR.get(pdf_name)
        if expected_vendor and invoice.get("vendor_name") != expected_vendor:
            raise AssertionError(
                f"vendor_name {invoice.get('vendor_name')!r} != {expected_vendor!r}"
            )
        expected_ids = ALLMOXY_EXPECTED_ITEM_IDS.get(pdf_name)
        if expected_ids:
            found_ids = {item["id"] for item in invoice["line_items"]}
            missing_ids = expected_ids - found_ids
            if missing_ids:
                raise AssertionError(f"missing line item ids: {sorted(missing_ids)}")

    if pdf_name and pdf_name.startswith("eb"):
        _validate_edgebanding_result(invoice, pdf_path=pdf_path)

    expected_eb = EDGEBANDING_EXPECTED.get(pdf_name)
    if pdf_name and pdf_name.startswith("eb") and not expected_eb:
        raise AssertionError(f"missing EDGEBANDING_EXPECTED for {pdf_name}")
    if expected_eb:
        for field in ("invoice_number", "cust_po", "date_ordered", "ship_date"):
            if invoice.get(field) != expected_eb[field]:
                raise AssertionError(
                    f"{field} {invoice.get(field)!r} != {expected_eb[field]!r}"
                )
        got_total = float(invoice.get("invoice_total") or 0)
        if abs(got_total - float(expected_eb["invoice_total"])) > 0.02:
            raise AssertionError(
                f"invoice_total {got_total!r} != {expected_eb['invoice_total']!r}"
            )
        item_count = expected_eb.get("item_count", 1)
        if len(invoice["line_items"]) != item_count:
            raise AssertionError(
                f"expected {item_count} line items, got {len(invoice['line_items'])}"
            )
        items_by_id = {item["id"]: item for item in invoice["line_items"]}
        expected_items = expected_eb.get("items")
        if expected_items:
            for item_id, checks in expected_items.items():
                item = items_by_id.get(item_id)
                if not item:
                    raise AssertionError(f"missing line item {item_id!r}")
                if item["qty"] != checks["qty"]:
                    raise AssertionError(
                        f"{item_id} qty {item['qty']!r} != {checks['qty']!r}"
                    )
                if abs(float(item["total_price"]) - checks["total_price"]) > 0.02:
                    raise AssertionError(
                        f"{item_id} total {item['total_price']!r} != {checks['total_price']!r}"
                    )
                if checks["name_contains"] not in (item.get("name") or ""):
                    raise AssertionError(
                        f"{item_id} name missing {checks['name_contains']!r}"
                    )
        else:
            item = invoice["line_items"][0]
            if item["id"] != expected_eb["item_id"]:
                raise AssertionError(f"item id {item['id']!r} != {expected_eb['item_id']!r}")
            if item["qty"] != expected_eb["qty"]:
                raise AssertionError(f"qty {item['qty']!r} != {expected_eb['qty']!r}")
            if abs(float(item["unit_price"]) - expected_eb["unit_price"]) > 0.001:
                raise AssertionError(
                    f"unit_price {item['unit_price']!r} != {expected_eb['unit_price']!r}"
                )
            if expected_eb["name_contains"] not in (item.get("name") or ""):
                raise AssertionError(
                    f"name {item.get('name')!r} missing {expected_eb['name_contains']!r}"
                )

    expected_wurth = WURTH_EXPECTED.get(pdf_name)
    if expected_wurth:
        if invoice.get("invoice_number") != expected_wurth["invoice_number"]:
            raise AssertionError(
                f"invoice_number {invoice.get('invoice_number')!r} != "
                f"{expected_wurth['invoice_number']!r}"
            )
        exp_total = float(expected_wurth["invoice_total"])
        got_total = float(invoice.get("invoice_total") or 0)
        if abs(got_total - exp_total) > 0.02:
            raise AssertionError(
                f"invoice_total {got_total!r} != {exp_total!r}"
            )
        if len(invoice["line_items"]) != expected_wurth["item_count"]:
            raise AssertionError(
                f"expected {expected_wurth['item_count']} line items, "
                f"got {len(invoice['line_items'])}"
            )
        found_parts = {item["id"] for item in invoice["line_items"]}
        if not expected_wurth["part_ids"] <= found_parts:
            raise AssertionError(
                f"missing part ids: {expected_wurth['part_ids'] - found_parts}"
            )
        line_sum = sum(float(item["total_price"]) for item in invoice["line_items"])
        subtotal = expected_wurth.get("subtotal")
        if subtotal is not None and abs(line_sum - subtotal) > 0.02:
            raise AssertionError(
                f"line item total {line_sum:.2f} != subtotal {subtotal:.2f}"
            )


def main():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    failures = []

    try:
        _check_eb_test_coverage(test_dir)
    except AssertionError as exc:
        print(f"FAIL edgebanding test coverage          {exc}")
        sys.exit(1)

    for pdf_name, parser_name in sorted(PDF_PARSER_MAP.items()):
        pdf_path = os.path.join(test_dir, pdf_name)
        parser = getattr(parsers, parser_name)
        try:
            raw = parser(pdf_path)
            result = parsers.normalize_parser_output(
                raw, vendor_name=getattr(parser, "name", None)
            )
            validate_result(result, pdf_name=pdf_name, pdf_path=pdf_path)
            vendor = result.get("vendor_name") or "-"
            invoices = result["invoices"]
            inv_nums = ", ".join(
                inv.get("invoice_number") or "?" for inv in invoices[:3]
            )
            if len(invoices) > 3:
                inv_nums += ", ..."
            item_count = sum(len(inv["line_items"]) for inv in invoices)
            first = invoices[0]
            print(
                f"OK  {pdf_name:<22} {parser_name:<35} "
                f"invoices={len(invoices):>2}  items={item_count:>3}  "
                f"inv=[{inv_nums}]  "
                f"vendor={vendor[:28]:<28}  "
                f"total={first.get('invoice_total') or '-'}"
            )
        except Exception as exc:
            failures.append((pdf_name, parser_name, str(exc)))
            print(f"FAIL {pdf_name:<22} {parser_name:<35} {exc}")

    wurth_page_failures = []
    for pdf_name in sorted(PDF_PARSER_MAP):
        if not pdf_name.startswith("wurth"):
            continue
        pdf_path = os.path.join(test_dir, pdf_name)
        try:
            doc = fitz.open(pdf_path)
            validate_wurth_all_pages(pdf_path)
            if len(doc) > 1:
                print(
                    f"OK  {pdf_name:<22} (all {len(doc)} pages validated)"
                )
        except Exception as exc:
            wurth_page_failures.append((pdf_name, str(exc)))
            print(f"FAIL {pdf_name:<22} multi-page validation       {exc}")

    print()
    total_failures = len(failures) + len(wurth_page_failures)
    print(f"Passed: {len(PDF_PARSER_MAP) - len(failures)} / {len(PDF_PARSER_MAP)}")
    if wurth_page_failures:
        print(f"Wurth page failures: {len(wurth_page_failures)}")
    if failures or wurth_page_failures:
        print("\nFailures:")
        for pdf_name, parser_name, err in failures:
            print(f"  {pdf_name} ({parser_name}): {err}")
        for pdf_name, err in wurth_page_failures:
            print(f"  {pdf_name} (all pages): {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
