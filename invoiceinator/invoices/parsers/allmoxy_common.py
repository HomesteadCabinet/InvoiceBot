"""Shared Allmoxy-style order PDF line-item parsing."""

import re

from .pdf import value_after
from .schema import make_line_item, normalize_dimension

_ALLMOXY_ID_RE = re.compile(r"^\d+\s+\d{2}$")
_ALLMOXY_TABLE_HEADERS = frozenset({"Qty", "Width", "Height", "Cab #", "Price", "Total"})
_ALLMOXY_AMOUNT_RE = re.compile(r"^\$[\d,]+(?:\.\d{1,2})?$")
_ALLMOXY_NOTE_RE = re.compile(
    r"^(Lites Wide|Lites High|Panels Wide|Product Description|Comment|Line Comments):",
    re.IGNORECASE,
)
_INVOICE_HEADER_RE = re.compile(r"^Invoice\s*#", re.IGNORECASE)
_ALLMOXY_VENDOR_BLOCK_STOP = frozenset({"Bill To:", "Ship To:"})
_PHONE_RE = re.compile(r"^\(\d{3}\)\s*\d{3}-\d{4}$")
_CITY_STATE_ZIP_RE = re.compile(r"^[A-Za-z].*,\s*[A-Z]{2}\s+\d{5}(-\d{4})?$")
# Product block titles (Cope & Stick Door:, Drawer Front:, etc.) — not field labels like Comment:
_PRODUCT_SECTION_RE = re.compile(
    r"(Door|Drawer|Panel|Mullion|Material|Folder|Slab|End Panel|Glass)",
    re.IGNORECASE,
)


def _parse_fractional_inches(value):
    """Parse Allmoxy dimensions: ``14``, ``17 3/4``, ``19 3/8``."""
    s = str(value).strip()
    if not s:
        return None
    mixed = re.match(r"^(\d+)\s+(\d+)/(\d+)$", s)
    if mixed:
        whole = int(mixed.group(1)) + int(mixed.group(2)) / int(mixed.group(3))
        return normalize_dimension(whole)
    simple_frac = re.match(r"^(\d+)/(\d+)$", s)
    if simple_frac:
        return normalize_dimension(int(simple_frac.group(1)) / int(simple_frac.group(2)))
    return normalize_dimension(s)


def _allmoxy_is_config_label(line):
    """Labels that end with ``:`` but are not product section titles."""
    s = line.strip().rstrip(":").strip()
    prefixes = (
        "Bill To", "Ship To", "Order Name", "Order Status", "Date Paid",
        "Amount Paid", "Date Ordered", "Payment Due", "Projected Ship",
        "Ship Date", "Shipping Method", "Wood Type", "Door Style", "Panel Face",
        "Panel Profile", "Stile & Rail", "Stile &", "Edge Profile",
        "Hinge Drilling", "Top Rail", "Bottom Rail", "Left Stile",
        "Right Stile", "Middle Rail", "Middle Stile", "Vert. Rail",
        "Horiz. Rail", "Section Comments", "Line Comments", "Part Type",
        "Premium Door", "Notes", "Signature", "Subtotal", "Tax", "Shipping",
        "Total", "Remit", "Payment History", "Total Due", "Date",
        "Comment", "Profile", "Room Name", "Thickness", "Core", "Face",
        "Order Totals", "Tracking Number",
    )
    return any(s.startswith(p.rstrip(":")) for p in prefixes)


def _allmoxy_section_name(line):
    if "Folder" in line:
        name = line.rstrip(":").strip()
        return re.sub(r"^[\uf07b\uf115\s]+", "", name).strip()
    if line.endswith(":") and not _allmoxy_is_config_label(line):
        if _PRODUCT_SECTION_RE.search(line):
            return line.rstrip(":").strip()
    return ""


def _allmoxy_section_before_id(lines, id_idx):
    if id_idx > 0:
        return _allmoxy_section_name(lines[id_idx - 1])
    return ""


def _allmoxy_read_table_header_end(lines, id_idx):
    """Return index of first data row (after Price/Total header lines)."""
    j = id_idx + 1
    while j < len(lines):
        if lines[j] == "Price":
            j += 1
            if j < len(lines) and lines[j] == "Total":
                j += 1
            return j
        j += 1
    return id_idx + 1


def _allmoxy_header_has_dims(lines, id_idx, price_idx):
    return any(lines[k] == "Width" for k in range(id_idx + 1, price_idx))


def _allmoxy_collect_notes(lines, i):
    notes = []
    while i < len(lines):
        line = lines[i]
        if _ALLMOXY_ID_RE.match(line):
            break
        if "Total Item" in line or line in ("Total Items", "Total Item"):
            break
        if _ALLMOXY_NOTE_RE.match(line) or line.startswith("Product Description:"):
            if line.rstrip().endswith(":") and i + 1 < len(lines):
                nxt = lines[i + 1]
                if not _ALLMOXY_ID_RE.match(nxt) and not _ALLMOXY_AMOUNT_RE.match(nxt):
                    if "Total Item" not in nxt:
                        notes.append(f"{line} {nxt}")
                        i += 2
                        continue
            notes.append(line)
            i += 1
            continue
        if _ALLMOXY_AMOUNT_RE.match(line):
            break
        break
    return notes, i


def _parse_allmoxy_style_line_items(lines, section_name=""):
    """
    Parse Allmoxy order PDFs: repeated ``ID`` tables per folder, with or without
    Width/Height columns, optional Cab # and trailing note lines per item.
    """
    items = []
    current_section = section_name or ""
    i = 0

    while i < len(lines):
        line = lines[i]
        folder = _allmoxy_section_name(line)
        if folder:
            current_section = folder

        if line != "ID":
            i += 1
            continue

        section = _allmoxy_section_before_id(lines, i)
        if section:
            current_section = section

        price_idx = i + 1
        while price_idx < len(lines) and lines[price_idx] != "Price":
            price_idx += 1
        has_dims = _allmoxy_header_has_dims(lines, i, price_idx)
        i = _allmoxy_read_table_header_end(lines, i)

        while i < len(lines):
            if "Total Item" in lines[i] or lines[i] in ("Total Items", "Total Item"):
                break
            # Page/Order # footers often appear mid-table in PDF text order — skip, do not stop.
            if lines[i].startswith("Page ") or lines[i].startswith("Order #"):
                i += 1
                continue
            if not _ALLMOXY_ID_RE.match(lines[i]):
                i += 1
                continue

            item_id = lines[i]
            i += 1
            qty = lines[i] if i < len(lines) else "1"
            i += 1
            width = length = height = None
            cab = ""
            desc_parts = []

            if has_dims:
                if i < len(lines):
                    width = _parse_fractional_inches(lines[i])
                    i += 1
                if i < len(lines):
                    length = height = _parse_fractional_inches(lines[i])
                    i += 1

            cab_candidates = []
            while i < len(lines) and not _ALLMOXY_AMOUNT_RE.match(lines[i]):
                if re.match(r"^\d+$", lines[i]):
                    cab_candidates.append(lines[i])
                i += 1
            if cab_candidates:
                cab = cab_candidates[-1]

            if i + 1 >= len(lines) or not _ALLMOXY_AMOUNT_RE.match(lines[i]):
                continue
            unit_price = lines[i]
            i += 1
            if i >= len(lines) or not _ALLMOXY_AMOUNT_RE.match(lines[i]):
                continue
            total_price = lines[i]
            i += 1

            notes, i = _allmoxy_collect_notes(lines, i)
            if cab:
                desc_parts.append(f"Cab #{cab}")
            desc_parts.extend(notes)
            description = " ".join(desc_parts)

            items.append(
                make_line_item(
                    item_id=item_id,
                    name=current_section or "Item",
                    description=description,
                    qty=qty,
                    width=width,
                    length=length,
                    height=height,
                    unit_price=unit_price,
                    total_price=total_price,
                )
            )

        i = _allmoxy_skip_past_table_footer(lines, i)
        continue

    return items


def _allmoxy_skip_past_table_footer(lines, i):
    """Advance past ``Total Item(s)``, section subtotals, and config lines to the next table."""
    while i < len(lines):
        line = lines[i]
        if line == "ID":
            break
        if _allmoxy_section_name(line):
            break
        if line.startswith("Page ") or line.startswith("Order #"):
            break
        if "Total Item" in line:
            i += 1
            if i < len(lines) and _ALLMOXY_AMOUNT_RE.match(lines[i]):
                i += 1
            continue
        i += 1
    return i


def _allmoxy_is_vendor_address_line(line):
    """Phone, street, or country lines between seller name and Bill To."""
    s = line.strip()
    if not s:
        return True
    if s == "United States":
        return True
    if s.startswith("PO#") or s.startswith("Tracking Number"):
        return True
    if _PHONE_RE.match(s):
        return True
    if _CITY_STATE_ZIP_RE.match(s):
        return True
    if re.match(r"^\d+\s+\S+", s) and re.search(
        r"\b(Circle|Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Blvd|Drive|Dr\.?|Lane|Ln\.?|Way|Highway|Hwy)\b",
        s,
        re.I,
    ):
        return True
    return False


def _allmoxy_looks_like_company_name(line):
    """True if line is likely the selling company's name (not customer/metadata)."""
    s = line.strip()
    if not s or len(s) < 2:
        return False
    if s.endswith(":"):
        return False
    if _INVOICE_HEADER_RE.match(s):
        return False
    if s in ("Order Totals", "Signature", "X", "Date:"):
        return False
    if _allmoxy_is_vendor_address_line(s):
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    if _allmoxy_is_config_label(s + ":"):
        return False
    return True


def _allmoxy_extract_vendor_name(lines):
    """
    Extract the cabinet shop / mill name from Allmoxy-export PDFs.

    Layout varies by exporter: often ``Invoice #`` then seller name (optional
    phone/address) then ``Bill To:`` (customer). Some PDFs omit the seller block.
    """
    vendor = None
    for i, line in enumerate(lines):
        if not _INVOICE_HEADER_RE.match(line):
            continue
        j = i + 1
        while j < len(lines) and lines[j] not in _ALLMOXY_VENDOR_BLOCK_STOP:
            candidate = lines[j].strip()
            if _allmoxy_looks_like_company_name(candidate):
                vendor = candidate
                break
            j += 1
    return vendor


def _allmoxy_labeled_date(lines, label):
    for line in lines:
        if label in line:
            m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", line)
            if m:
                return m.group(1)
    return None


def _allmoxy_fill_invoice_metadata(result, lines, full_text):
    """Populate header fields common to Allmoxy-export PDF layouts."""
    vendor = _allmoxy_extract_vendor_name(lines)
    if vendor:
        result["vendor_name"] = vendor

    m = re.search(r"Invoice #\s*(\d+)", full_text)
    if m:
        result["invoice_number"] = m.group(1)
    if not result["invoice_number"]:
        inv = value_after(lines, "Invoice #")
        if inv:
            m = re.search(r"\d+", inv)
            if m:
                result["invoice_number"] = m.group(0)

    result["ship_date"] = (
        _allmoxy_labeled_date(lines, "Projected Ship Date")
        or _allmoxy_labeled_date(lines, "Ship Date")
    )
    result["date_ordered"] = _allmoxy_labeled_date(lines, "Date Ordered")
    result["invoice_due_date"] = _allmoxy_labeled_date(lines, "Payment Due By")

    for idx, line in enumerate(lines):
        if line.startswith("Order Name:"):
            po_parts = [line.split(":", 1)[1].strip()]
            j = idx + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.startswith(
                    (
                        "Order Status",
                        "Date Ordered",
                        "Payment Due",
                        "Projected Ship",
                        "Shipping Method",
                    )
                ):
                    break
                po_parts.append(nxt)
                j += 1
            result["cust_po"] = " ".join(po_parts).strip()
            break

    m = re.search(r"Total:\s*\$?([\d,]+\.\d{1,2})", full_text)
    if m:
        result["invoice_total"] = m.group(1).replace(",", "")
    elif value_after(lines, "Total Due:"):
        m = re.search(r"([\d,]+\.\d{1,2})", value_after(lines, "Total Due:"))
        if m:
            result["invoice_total"] = m.group(1).replace(",", "")
