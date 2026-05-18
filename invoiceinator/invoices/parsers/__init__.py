"""
Vendor-specific PDF invoice parsers.

Each ``parse_*_invoice(pdf_path)`` returns a single invoice dict (or, for Wurth,
``{"vendor_name", "invoices": [...]}``). The API normalizes all parser output via
``normalize_parser_output()`` to:

    {"vendor_name": "...", "invoices": [<invoice dict>, ...]}

Each invoice: invoice_number, ship_date, date_ordered, vendor_name, invoice_total,
invoice_due_date, cust_po, line_items.

Each line item: id, name, description, qty, unit, unit_price, total_price,
width, length, height.
"""

from .allmoxy import parse_allmoxy_invoice
from .american_saw import parse_american_saw_invoice
from .bitdefender import parse_bitdefender_invoice
from .crexendo import parse_crexendo_invoice
from .edgebanding_services import parse_edgebanding_services_invoice
from .hafele import parse_hafele_invoice
from .high_mountain import parse_high_mountain_invoice
from .industrial_tool_supply import parse_industrial_tool_supply_invoice
from .intermountain import parse_intermountain_invoice
from .schema import (
    INVOICE_FIELDS,
    LINE_ITEM_ALIASES,
    PARSER_OUTPUT_FIELDS,
    empty_invoice,
    invoice_bundle,
    make_line_item,
    normalize_dimension,
    normalize_invoice,
    normalize_line_item,
    normalize_parser_output,
    to_float,
)
from .sierra import parse_sierra_invoice
from .wi_fiber import parse_wi_fiber_invoice
from .wurth import parse_wurth_invoice

__all__ = [
    "INVOICE_FIELDS",
    "LINE_ITEM_ALIASES",
    "PARSER_OUTPUT_FIELDS",
    "empty_invoice",
    "invoice_bundle",
    "make_line_item",
    "normalize_dimension",
    "normalize_invoice",
    "normalize_line_item",
    "normalize_parser_output",
    "to_float",
    "list_invoice_parsers",
    "parse_allmoxy_invoice",
    "parse_american_saw_invoice",
    "parse_bitdefender_invoice",
    "parse_crexendo_invoice",
    "parse_edgebanding_services_invoice",
    "parse_hafele_invoice",
    "parse_high_mountain_invoice",
    "parse_industrial_tool_supply_invoice",
    "parse_intermountain_invoice",
    "parse_sierra_invoice",
    "parse_wi_fiber_invoice",
    "parse_wurth_invoice",
]

_PARSER_FUNCTIONS = [
    parse_allmoxy_invoice,
    parse_american_saw_invoice,
    parse_bitdefender_invoice,
    parse_crexendo_invoice,
    parse_edgebanding_services_invoice,
    parse_hafele_invoice,
    parse_high_mountain_invoice,
    parse_industrial_tool_supply_invoice,
    parse_intermountain_invoice,
    parse_sierra_invoice,
    parse_wi_fiber_invoice,
    parse_wurth_invoice,
]


def list_invoice_parsers():
    """
    Return vendor parser callables exposed to the API.

    Only functions named parse_* with a display ``.name`` attribute are included.
    """
    parsers = []
    for func in _PARSER_FUNCTIONS:
        if not func.__name__.startswith("parse_"):
            continue
        display_name = getattr(func, "name", None)
        if not display_name or not isinstance(display_name, str):
            continue
        parsers.append({"method": func.__name__, "name": display_name})
    return sorted(parsers, key=lambda entry: entry["name"].lower())


# Register parse_* exports dynamically for getattr(parsers, "parse_*")
for _func in _PARSER_FUNCTIONS:
    globals()[_func.__name__] = _func
