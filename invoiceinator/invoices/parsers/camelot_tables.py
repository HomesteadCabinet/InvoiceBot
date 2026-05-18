"""Camelot table extraction for code-based invoice tables."""

import re

import camelot

def _parse_camelot_code_tables(pdf_path):
    """Extract line items from tables whose header row contains 'code'."""
    line_items = []

    def dynamic_line_item_parser(df):
        header_row = df.iloc[0].tolist()
        header_map = {}
        for idx, col in enumerate(header_row):
            col_lower = str(col).strip().lower()
            if "code" in col_lower:
                header_map["id"] = idx
            if "description" in col_lower:
                header_map["description"] = idx
            if re.search(r"\bordered\b", col_lower) or re.search(r"\bshipped\b", col_lower):
                header_map["qty"] = idx
            if "unit price" in col_lower:
                header_map["unit_price"] = idx
            if (("ext" in col_lower) or ("total price" in col_lower)) and not col_lower.startswith("total"):
                header_map["total_price"] = idx
            if "unit" in col_lower and "price" not in col_lower:
                header_map["unit"] = idx

        items = []
        for i in range(1, len(df)):
            row = df.iloc[i].tolist()
            first_cell = str(row[0]).strip().lower()
            if first_cell.startswith("total"):
                break
            row_text = " ".join(str(cell) for cell in row if cell)
            if not re.search(r"\d", row_text):
                continue

            item = {}
            for key, col_idx in header_map.items():
                cell_val = str(row[col_idx]).strip() if col_idx < len(row) else ""
                parts = [s.strip() for s in re.split(r"[\n\r]+", cell_val) if s.strip()]
                item[key] = " ".join(parts)

            if item.get("description"):
                desc_parts = [p.strip() for p in re.split(r"[\n\r]+", item["description"]) if p.strip()]
                if not item.get("name"):
                    item["name"] = desc_parts[0] if desc_parts else ""
                item["description"] = " ".join(desc_parts[1:]) if len(desc_parts) > 1 else ""

            if item.get("id") or item.get("description"):
                items.append(item)
        return items

    tables = []
    for flavor in ("lattice", "stream"):
        try:
            tables.extend(camelot.read_pdf(pdf_path, pages="all", flavor=flavor))
        except Exception:
            pass

    for table in tables:
        header_row_text = " ".join(str(x) for x in table.df.iloc[0].tolist()).lower()
        if "code" in header_row_text:
            line_items.extend(dynamic_line_item_parser(table.df))
    return line_items
