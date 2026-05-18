"""Allmoxy invoice parser."""

from .allmoxy_common import _allmoxy_fill_invoice_metadata, _parse_allmoxy_style_line_items
from .pdf import pdf_lines, pdf_text
from .schema import empty_invoice, normalize_invoice


def parse_allmoxy_invoice(pdf_path):
    """
    Allmoxy order/invoice PDFs (allmoxy*.pdf test fixtures).

    Supports multiple line-item table layouts per document: Width/Height columns,
    optional Cab # and extra columns (Panels Wide, Hinge, etc.), qty-only rows,
    split multi-line headers, Folder or product-type section titles, and $0.00 lines.
    """
    lines = pdf_lines(pdf_path)
    full_text = pdf_text(pdf_path)
    result = empty_invoice("Allmoxy")  # fallback when PDF has no seller block
    _allmoxy_fill_invoice_metadata(result, lines, full_text)
    result["line_items"] = _parse_allmoxy_style_line_items(lines)
    return normalize_invoice(result)


parse_allmoxy_invoice.name = "Allmoxy"
