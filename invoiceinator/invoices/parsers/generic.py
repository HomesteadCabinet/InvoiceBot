"""Generic invoice parser fallback.

The generic parser first tries known vendor-specific parsers using text cues,
then falls back to a layout-agnostic parser that handles common invoice table
shapes like QuickBooks exports and simple line-item summaries.
"""

from __future__ import annotations

import os
import re

from .advanced_machinery import parse_advanced_machinery_invoice
from .allmoxy import parse_allmoxy_invoice
from .american_saw import parse_american_saw_invoice
from .bitdefender import parse_bitdefender_invoice
from .crexendo import parse_crexendo_invoice
from .edgebanding_services import parse_edgebanding_services_invoice
from .element_designs import parse_element_designs_invoice
from .hafele import parse_hafele_invoice
from .high_mountain import parse_high_mountain_invoice
from .mcmaster_carr import parse_mcmaster_carr_invoice
from .industrial_tool_supply import parse_industrial_tool_supply_invoice
from .intermountain import parse_intermountain_invoice
from .ipaco import parse_ipaco_invoice
from .pdf import pdf_lines, pdf_text
from .rugby import parse_rugby_invoice
from .weinig import parse_weinig_invoice
from .schema import empty_invoice, make_line_item, normalize_invoice, normalize_parser_output, to_float
from .sierra import parse_sierra_invoice
from .sherwin import parse_sherwin_invoice
from .wi_fiber import parse_wi_fiber_invoice
from .wurth import parse_wurth_invoice
from .yates_mouldings import parse_yates_mouldings_invoice

_PARSER_CANDIDATES = (
    parse_advanced_machinery_invoice,
    parse_allmoxy_invoice,
    parse_american_saw_invoice,
    parse_bitdefender_invoice,
    parse_crexendo_invoice,
    parse_edgebanding_services_invoice,
    parse_element_designs_invoice,
    parse_hafele_invoice,
    parse_high_mountain_invoice,
    parse_mcmaster_carr_invoice,
    parse_industrial_tool_supply_invoice,
    parse_intermountain_invoice,
    parse_ipaco_invoice,
    parse_rugby_invoice,
    parse_weinig_invoice,
    parse_sierra_invoice,
    parse_sherwin_invoice,
    parse_wi_fiber_invoice,
    parse_wurth_invoice,
    parse_yates_mouldings_invoice,
)

_COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:inc\.?|llc|l\.l\.c\.|co\.?|company|corp\.?|corporation|ltd\.?|limited)\b",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"^\$?-?[\d,]+\.\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")
_ITEM_INDEX_RE = re.compile(r"^\d+\.$")
_STOP_RE = re.compile(
    r"^(subtotal|total|balance due|thank you|ways to pay|page \d+ of \d+|remit)\b",
    re.IGNORECASE,
)
_HEADER_PATTERNS = (
    ("item code", "description", "quantity", "price each", "amount"),
    ("product or service", "description", "qty", "rate", "amount"),
    ("date", "activity", "qty", "rate", "amount"),
    ("code", "description", "qty", "unit price", "amount"),
)
_VENDOR_LABELS = {
    "INVOICE",
    "INVOICE #",
    "INVOICE NO",
    "INVOICE NO.",
    "INVOICE DETAILS",
    "DATE",
    "DUE DATE",
    "SALES REP",
    "CONTACT/PHONE NUMBER",
    "TERMS",
    "PROJECT",
    "TOTAL",
    "SUBTOTAL",
    "BALANCE DUE",
    "P.O. NUMBER",
    "PO NUMBER",
    "BILL TO",
    "SHIP TO",
    "PRODUCT OR SERVICE",
    "DESCRIPTION",
    "QTY",
    "RATE",
    "AMOUNT",
    "#",
    "WAYS TO PAY",
    "PAGE 1 OF 1",
    "CUSTOMER SIGNATURE",
}


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug or "item"


def _looks_like_money(value):
    return bool(_MONEY_RE.match(_clean_text(value).replace(",", "").replace("$", "")) or _MONEY_RE.match(_clean_text(value)))


def _normalized_money(value):
    return _clean_text(value).replace("$", "").replace(",", "")


def _is_stop_line(line):
    text = _clean_text(line)
    upper = text.upper()
    return not text or bool(_STOP_RE.match(text)) or upper in {
        "BILL TO",
        "SHIP TO",
        "INVOICE",
        "INVOICE DETAILS",
        "WAYS TO PAY",
        "DATE",
        "ACTIVITY",
        "QTY",
        "RATE",
        "AMOUNT",
        "#",
        "PRODUCT OR SERVICE",
        "DESCRIPTION",
        "PRICE",
        "TOTAL",
        "SUBTOTAL",
        "BALANCE DUE",
    } or upper.startswith("INVOICE")


def _company_score(line):
    text = _clean_text(line)
    if not text:
        return -999
    score = 0
    if text.upper().startswith("INVOICE"):
        score -= 20
    if text.upper() in _VENDOR_LABELS:
        score -= 20
    if _COMPANY_SUFFIX_RE.search(text):
        score += 6
    if text.upper() == text and len(text.split()) >= 2:
        score += 2
    if any(ch.isalpha() for ch in text):
        score += 1
    if any(ch.isdigit() for ch in text):
        score -= 2
    if re.search(r"[@/]|https?://|www\.", text, re.IGNORECASE):
        score -= 4
    if re.match(r"^\d{1,5}\s+\w+", text):
        score -= 2
    if len(text.split()) > 6:
        score -= 4
    if len(text) > 55:
        score -= 4
    if text.endswith("."):
        score -= 2
    if re.search(
        r"finance charge|credit card processing fee|balance outstanding|attorney|thank you for your business",
        text,
        re.IGNORECASE,
    ):
        score -= 10
    if _STOP_RE.match(text):
        score -= 10
    return score


def _extract_vendor_name(lines, text):
    cutoffs = []
    for idx, line in enumerate(lines):
        upper = _clean_text(line).upper()
        if upper.startswith("BILL TO") or upper.startswith("SHIP TO"):
            cutoffs.append(idx)
            break
    search_limit = cutoffs[0] if cutoffs else min(len(lines), 40)

    best_line = ""
    best_score = -999
    for idx, line in enumerate(lines[:search_limit]):
        text_line = _clean_text(line)
        if not text_line or _is_stop_line(text_line):
            continue
        score = _company_score(text_line)
        if score > best_score:
            best_score = score
            best_line = text_line

    if best_score >= 1:
        return best_line

    for line in lines:
        text_line = _clean_text(line)
        if not text_line or _is_stop_line(text_line):
            continue
        if _COMPANY_SUFFIX_RE.search(text_line):
            return text_line

    for line in lines:
        text_line = _clean_text(line)
        if not text_line or _is_stop_line(text_line):
            continue
        if text_line.isupper() and len(text_line.split()) >= 2:
            return text_line

    return ""


def _extract_value_by_pattern(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            value = m.group(1).strip()
            if value:
                return value
    return None


def _extract_invoice_number(text):
    return _extract_value_by_pattern(
        text,
        (
            r"Invoice\s*(?:#|no\.?|number)\s*[:.]?\s*([A-Za-z0-9-]+)",
            r"INVOICE\s*#\s*([A-Za-z0-9-]+)",
            r"Invoice\s+no\.?\s*[:.]?\s*([A-Za-z0-9-]+)",
        ),
    )


def _extract_date_value(text, label_patterns):
    return _extract_value_by_pattern(text, label_patterns)


def _extract_total(text):
    return _extract_value_by_pattern(
        text,
        (
            r"(?:BALANCE DUE|INVOICE TOTAL|TOTAL DUE|TOTAL|SUBTOTAL)\s*\n\s*\$?(-?[\d,]+\.\d{2})",
            r"(?:BALANCE DUE|INVOICE TOTAL|TOTAL DUE|TOTAL|SUBTOTAL)\s*[:.]?\s*\$?(-?[\d,]+\.\d{2})",
        ),
    )


def _find_table_start(lines):
    lowered = [_clean_text(line).lower() for line in lines]
    for pattern in _HEADER_PATTERNS:
        cursor = 0
        last_index = -1
        matched = True
        for token in pattern:
            found = False
            for idx in range(cursor, len(lowered)):
                if token in lowered[idx]:
                    last_index = idx
                    cursor = idx + 1
                    found = True
                    break
            if not found:
                matched = False
                break
        if matched and last_index >= 0:
            return last_index + 1
    return -1


def _collect_item_blocks(lines, start_idx):
    blocks = []
    current = []
    numbered = False
    for line in lines[start_idx:]:
        text_line = _clean_text(line)
        if _is_stop_line(text_line):
            if current:
                blocks.append(current)
            break
        if _ITEM_INDEX_RE.match(text_line):
            numbered = True
            if current:
                blocks.append(current)
            current = [text_line]
            continue
        if numbered and current and _ITEM_INDEX_RE.match(current[0]) and text_line.endswith(".") and text_line[:-1].isdigit():
            blocks.append(current)
            current = [text_line]
            continue
        if not current and not text_line:
            continue
        current.append(text_line)

    if current:
        blocks.append(current)

    if not numbered and blocks:
        return [blocks[0]]
    return blocks


def _parse_block(block, item_index):
    lines = [line for line in (_clean_text(line) for line in block) if line]
    if not lines:
        return None

    item_id = ""
    if _ITEM_INDEX_RE.match(lines[0]):
        item_id = f"ROW-{lines[0].rstrip('.')}"
        lines = lines[1:]

    money_values = []
    while lines and _looks_like_money(lines[-1]):
        money_values.insert(0, _normalized_money(lines.pop()))

    qty = "1"
    if lines and re.fullmatch(r"-?[\d,]+(?:\.\d+)?", lines[-1]) and not _DATE_RE.match(lines[-1]):
        maybe_qty = lines[-1].replace(",", "")
        if lines[-1] != "" and len(maybe_qty) < 8:
            qty = maybe_qty
            lines.pop()

    if not lines and not money_values:
        return None

    if not item_id:
        item_id = _slugify(lines[0] if lines else f"item-{item_index}")

    name = lines[0] if lines else item_id
    description = " ".join(lines[1:]) if len(lines) > 1 else (lines[0] if lines else "")

    unit_price = 0.0
    total_price = 0.0
    if money_values:
        if len(money_values) == 1:
            total_price = to_float(money_values[0])
            unit_price = total_price
        else:
            unit_price = to_float(money_values[-2])
            total_price = to_float(money_values[-1])
    elif qty and re.fullmatch(r"-?[\d,]+(?:\.\d+)?", qty):
        total_price = 0.0
        unit_price = 0.0

    if total_price == 0.0 and unit_price and qty:
        total_price = to_float(qty) * unit_price

    return make_line_item(
        item_id=item_id,
        name=name,
        description=description,
        qty=qty,
        unit_price=unit_price,
        total_price=total_price,
    )


def _generic_fallback_parse(pdf_path):
    lines = pdf_lines(pdf_path)
    text = pdf_text(pdf_path)
    vendor_name = _extract_vendor_name(lines, text)
    result = empty_invoice(vendor_name or "Generic")

    result["invoice_number"] = _extract_invoice_number(text)
    result["date_ordered"] = _extract_date_value(
        text,
        (
            r"Invoice date\s*[:.]?\s*([0-9/.-]+)",
            r"Date ordered\s*[:.]?\s*([0-9/.-]+)",
            r"\bDATE\s*\n\s*([0-9/.-]+)",
        ),
    )
    result["ship_date"] = _extract_date_value(
        text,
        (
            r"Ship date\s*[:.]?\s*([0-9/.-]+)",
            r"\bShip\s*\n\s*([0-9/.-]+)",
        ),
    )
    result["invoice_due_date"] = _extract_date_value(
        text,
        (
            r"Due date\s*[:.]?\s*([0-9/.-]+)",
            r"Payment due\s*[:.]?\s*([0-9/.-]+)",
        ),
    )
    result["cust_po"] = _extract_value_by_pattern(
        text,
        (
            r"P\.?O\.?\s*Number\s*[:.]?\s*([^\n]+)",
            r"PO\s*Number\s*[:.]?\s*([^\n]+)",
            r"Project\s*[:.]?\s*([^\n]+)",
            r"Customer PO\s*[:.]?\s*([^\n]+)",
        ),
    )
    result["invoice_total"] = _extract_total(text)

    table_start = _find_table_start(lines)
    if table_start >= 0:
        blocks = _collect_item_blocks(lines, table_start)
        for idx, block in enumerate(blocks, start=1):
            parsed = _parse_block(block, idx)
            if parsed:
                result["line_items"].append(parsed)

    if not result["line_items"]:
        money_lines = [line for line in lines if _looks_like_money(line)]
        if len(money_lines) >= 2:
            result["line_items"].append(
                make_line_item(
                    item_id=_slugify(result.get("invoice_number") or os.path.basename(pdf_path)),
                    name=result.get("vendor_name") or "Invoice",
                    description=result.get("cust_po") or "",
                    qty="1",
                    unit_price=money_lines[-2],
                    total_price=money_lines[-1],
                )
            )

    return normalize_invoice(result)


def _candidate_sort_key(parser, text_lower):
    name = getattr(parser, "name", "") or ""
    tokens = [token for token in re.split(r"[\s&/,-]+", name.lower()) if len(token) > 2]
    score = sum(1 for token in tokens if token and token in text_lower)
    return (-score, name.lower(), parser.__name__)


def _score_result(result):
    if isinstance(result, dict) and "invoices" in result:
        invoices = result.get("invoices") or []
    elif isinstance(result, dict):
        invoices = [result]
    else:
        invoices = []
    if not invoices:
        return -999

    score = 0
    for invoice in invoices:
        line_items = invoice.get("line_items") or []
        if invoice.get("invoice_number"):
            score += 3
        if invoice.get("invoice_total"):
            score += 2
        if invoice.get("vendor_name"):
            score += 1
        if line_items:
            score += min(len(line_items), 8) * 2
            score += 2
            total = to_float(invoice.get("invoice_total"))
            line_sum = sum(to_float(item.get("total_price")) for item in line_items)
            if total and abs(line_sum - total) <= max(0.05, abs(total) * 0.05):
                score += 3
        else:
            score -= 6
    return score


def parse_generic_invoice(pdf_path):
    """
    Try the best available parser for ``pdf_path`` and fall back to a generic
    table/text parser when no vendor-specific parser fits.
    """
    text = pdf_text(pdf_path)
    text_lower = text.lower()

    ordered_parsers = sorted(_PARSER_CANDIDATES, key=lambda parser: _candidate_sort_key(parser, text_lower))

    best_result = None
    best_score = -999

    for parser in ordered_parsers:
        try:
            raw = parser(pdf_path)
            result = normalize_parser_output(raw, vendor_name=getattr(parser, "name", None))
            score = _score_result(result)
            if score > best_score:
                best_score = score
                best_result = result
        except Exception:
            continue

    generic_result = _generic_fallback_parse(pdf_path)
    generic_result_bundle = normalize_parser_output(
        generic_result,
        vendor_name=generic_result.get("vendor_name") or None,
    )
    generic_score = _score_result(generic_result_bundle)

    if generic_score >= best_score or best_result is None:
        return generic_result_bundle
    return best_result


parse_generic_invoice.name = "Generic"
