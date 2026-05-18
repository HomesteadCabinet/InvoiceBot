"""PDF text extraction via pymupdf."""

import re

import pymupdf as fitz


def pdf_lines(pdf_path):
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    return [line.strip() for line in text.splitlines() if line.strip()]


def pdf_text(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def value_after(lines, label):
    for i, line in enumerate(lines):
        if label.lower() in line.lower():
            parts = re.split(re.escape(label), line, flags=re.IGNORECASE, maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
            if i + 1 < len(lines):
                return lines[i + 1]
    return None
