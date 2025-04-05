# utils.py
import base64, os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import pdfplumber, re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from decimal import Decimal
import pytz
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/spreadsheets']



def get_gmail_service():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    return build('gmail', 'v1', credentials=creds)


def get_sheets_service():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    return build('sheets', 'v4', credentials=creds)


class DataExtractor:
    """Enhanced PDF data extraction utility with support for multiple extraction methods."""

    def __init__(self, pdf_path: str, debug: bool = False):
        """Initialize the DataExtractor with a PDF file path."""
        self.pdf_path = pdf_path
        self.pdf = pdfplumber.open(pdf_path)
        self.debug = debug
        self._log(f"Initialized DataExtractor for {pdf_path}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pdf.close()
        self._log("Closed PDF file")

    def _log(self, message: str):
        """Log messages if debug mode is enabled."""
        if self.debug:
            logger.info(message)

    def _pre_process_text(self, text: str, pre_processing: Optional[Dict[str, Any]] = None) -> str:
        """Apply pre-processing rules to text."""
        if not pre_processing:
            return text

        if pre_processing.get('remove_spaces'):
            text = re.sub(r'\s+', ' ', text)
        if pre_processing.get('to_uppercase'):
            text = text.upper()
        if pre_processing.get('remove_special_chars'):
            text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
        if pre_processing.get('remove_whitespace'):
            text = text.strip()

        self._log(f"Pre-processed text: {text}")
        return text

    def _post_process_text(self, text: str, data_type: str, post_processing: Optional[Dict[str, Any]] = None) -> Any:
        """Apply post-processing rules to extracted text."""
        if not post_processing:
            return text

        try:
            if data_type == 'date' and post_processing.get('format_date'):
                date = datetime.strptime(text, post_processing.get('input_format', '%Y-%m-%d'))
                result = date.strftime(post_processing['format_date'])

            elif data_type == 'currency':
                # Remove currency symbols and convert to decimal
                amount = Decimal(re.sub(r'[^\d.-]', '', text))
                if post_processing.get('round_decimals') is not None:
                    amount = amount.quantize(Decimal('0.01'))
                result = float(amount)

            elif data_type == 'number':
                number = float(re.sub(r'[^\d.-]', '', text))
                if post_processing.get('round_decimals') is not None:
                    number = round(number, post_processing['round_decimals'])
                result = number

            else:
                result = text

            self._log(f"Post-processed {data_type}: {result}")
            return result

        except (ValueError, TypeError) as e:
            self._log(f"Error post-processing {data_type}: {str(e)}")
            return text

    def _validate_text(self, text: str, rule: 'DataRule') -> bool:
        """Validate extracted text against rule constraints."""
        if rule.required and not text:
            self._log(f"Required field {rule.field_name} is empty")
            return False

        if rule.validation_regex:
            if not re.match(rule.validation_regex, text):
                self._log(f"Validation failed for {rule.field_name}: {text}")
                return False

        if rule.min_value is not None:
            try:
                value = float(text)
                if value < rule.min_value:
                    self._log(f"Value {value} below minimum {rule.min_value}")
                    return False
            except ValueError:
                self._log(f"Could not convert {text} to float for min_value validation")
                return False

        if rule.max_value is not None:
            try:
                value = float(text)
                if value > rule.max_value:
                    self._log(f"Value {value} above maximum {rule.max_value}")
                    return False
            except ValueError:
                self._log(f"Could not convert {text} to float for max_value validation")
                return False

        return True

    def _is_point_in_bbox(self, x: float, y: float, bbox: dict) -> bool:
        """Check if a point (x,y) is within a bounding box."""
        if not bbox:
            return True  # If no bbox specified, consider all points valid
        return (bbox['x'] <= x <= bbox['x'] + bbox['width'] and
                bbox['y'] <= y <= bbox['y'] + bbox['height'])

    def _extract_by_keyword(self, page, rule: 'DataRule') -> Optional[str]:
        """Extract text near a keyword."""
        if not rule.keyword:
            return None

        try:
            # Extract words and filter by bbox
            words = page.extract_words()
            filtered_words = []
            for word in words:
                if self._is_point_in_bbox(word['x0'], word['top'], rule.bbox):
                    filtered_words.append(word['text'])
            text = ' '.join(filtered_words)

            keyword_pos = text.find(rule.keyword)
            if keyword_pos == -1:
                self._log(f"Keyword '{rule.keyword}' not found")
                return None

            # Extract text after the keyword until the first newline
            start_pos = keyword_pos + len(rule.keyword)
            end_pos = text.find('\n', start_pos)
            if end_pos == -1:  # If no newline found, use the end of text
                end_pos = len(text)
            result = text[start_pos:end_pos].replace(':', '').strip()
            self._log(f"Extracted by keyword: {result}")
            return result
        except Exception as e:
            self._log(f"Error extracting by keyword: {str(e)}")
            return None

    def _extract_by_regex(self, page, rule: 'DataRule') -> Optional[str]:
        """Extract text using regex pattern."""
        if not rule.regex_pattern:
            return None

        try:
            # Extract words and filter by bbox
            words = page.extract_words()
            filtered_words = []
            for word in words:
                if self._is_point_in_bbox(word['x0'], word['top'], rule.bbox):
                    filtered_words.append(word['text'])
            text = ' '.join(filtered_words)

            match = re.search(rule.regex_pattern, text)
            result = match.group(0) if match else None
            self._log(f"Extracted by regex: {result}")
            return result
        except Exception as e:
            self._log(f"Error extracting by regex: {str(e)}")
            return None

    def _extract_by_table(self, page, rule: 'DataRule') -> Optional[str]:
        """Extract text from a table."""
        if not rule.table_config:
            return None

        try:
            tables = page.extract_tables()
            if not tables:
                self._log("No tables found on page")
                return None

            config = rule.table_config
            for table in tables:
                # Find the correct row/column based on header
                if config.get('header_text'):
                    for row_idx, row in enumerate(table):
                        if config['header_text'] in row:
                            if config.get('col_index') is not None:
                                result = table[row_idx + config.get('row_index', 1)][config['col_index']]
                                self._log(f"Extracted from table by header: {result}")
                                return result
                            break
                else:
                    # Direct row/column access
                    if config.get('row_index') is not None and config.get('col_index') is not None:
                        result = table[config['row_index']][config['col_index']]
                        self._log(f"Extracted from table by index: {result}")
                        return result
            return None
        except Exception as e:
            self._log(f"Error extracting from table: {str(e)}")
            return None

    def extract_line_items(self, page, rule: 'DataRule') -> List[Dict[str, Any]]:
        items = []
        header_row = None

        if rule.location_type == 'table':
            tables = page.extract_tables()
            for table in tables:
                # Find header row based on config or keyword
                header_row_idx = None
                item_columns = rule.table_config.get('item_columns', {})
                header_keyword = rule.table_config.get('header_text', 'code').lower()

                for idx, row in enumerate(table):
                    if row and any(cell and header_keyword in str(cell).lower() for cell in row):
                        header_row_idx = idx
                        header_row = row  # Store the header row

                        # Auto-detect item_columns if not explicitly provided
                        if not item_columns:
                            self._log(f"Auto-detecting item columns from header: {row}")
                            for col_idx, col in enumerate(row):
                                col_text = str(col).strip().lower()
                                if "code" in col_text:
                                    item_columns["id"] = col_idx
                                elif "desc" in col_text or "product" in col_text:
                                    item_columns["description"] = col_idx
                                elif "qty" in col_text or "quantity" in col_text:
                                    item_columns["quantity"] = col_idx
                                elif "unit" in col_text:
                                    item_columns["unit_price"] = col_idx
                                elif "ext" in col_text or "amount" in col_text or "total" in col_text:
                                    item_columns["amount"] = col_idx
                        break

                if header_row_idx is None or not item_columns:
                    continue  # No valid header found or failed to map columns

                for row in table[header_row_idx + rule.table_config.get('start_row_after_header', 1):]:
                    if not row or all(not (cell or '').strip() for cell in row):
                        continue  # Skip empty rows

                    item = {}
                    for key, col_idx in item_columns.items():
                        if col_idx < len(row):
                            item[key] = (row[col_idx] or '').strip()
                    if item:
                        items.append(item)

        elif rule.location_type == 'regex':
            # Extract words and filter by bbox
            words = page.extract_words()
            filtered_words = []
            for word in words:
                if self._is_point_in_bbox(word['x0'], word['top'], rule.bbox):
                    filtered_words.append(word['text'])
            text = ' '.join(filtered_words)

            pattern = re.compile(rule.regex_pattern)
            matches = pattern.findall(text)
            for match in matches:
                items.append({
                    'quantity': match[0],
                    'description': match[1],
                    'unit_price': match[2],
                    'amount': match[3],
                })

        return {
            'header_row': header_row,
            'items': items
        }

    def extract_data(self, rules: list['DataRule']) -> Dict[str, Any]:
        extracted_data = {}
        errors = []

        for rule in rules:
            if rule.data_type == 'line_items':
                line_items_data = {
                    'header_row': None,
                    'items': []
                }
                for page in self.pdf.pages:
                    result = self.extract_line_items(page, rule)
                    if result['header_row'] and not line_items_data['header_row']:
                        line_items_data['header_row'] = result['header_row']
                    if result['items']:
                        line_items_data['items'].extend(result['items'])
                if line_items_data['items']:
                    extracted_data[rule.field_name] = line_items_data
                elif rule.required:
                    errors.append(f"{rule.field_name} could not be extracted.")
            else:
                for page in self.pdf.pages:
                    text = None
                    # Use the appropriate extraction method based on location type
                    if rule.location_type == 'keyword':
                        text = self._extract_by_keyword(page, rule)
                    elif rule.location_type == 'regex':
                        text = self._extract_by_regex(page, rule)
                    elif rule.location_type == 'table':
                        text = self._extract_by_table(page, rule)
                    elif rule.location_type == 'header':
                        text = self._extract_by_table(page, rule)

                    if text:
                        text = self._pre_process_text(text, rule.pre_processing)
                        text = self._post_process_text(text, rule.data_type, rule.post_processing)
                        extracted_data[rule.field_name] = text
                        break
                if rule.required and rule.field_name not in extracted_data:
                    errors.append(f"{rule.field_name} could not be extracted.")

        if errors:
            raise ValueError(f"Extraction failed for fields: {', '.join(errors)}")

        return extracted_data

    def extract_tables(self, page_number: Optional[int] = None) -> List[List[List[str]]]:
        """
        Extract all tables from the PDF or from a specific page.

        Args:
            page_number: Optional page number (1-based index). If None, extracts from all pages.

        Returns:
            A list of tables, where each table is a list of rows, and each row is a list of cell values.
        """
        tables = []

        try:
            if page_number is not None:
                if 1 <= page_number <= len(self.pdf.pages):
                    page = self.pdf.pages[page_number - 1]
                    extracted = page.find_tables()
                    if extracted:
                        tables.extend(extracted)
                    self._log(f"Extracted {len(extracted)} tables from page {page_number}")
                else:
                    raise ValueError(f"Page number {page_number} is out of range")
            else:
                for idx, page in enumerate(self.pdf.pages, 1):
                    extracted = page.find_tables()
                    if extracted:
                        tables.extend(extracted)
                    self._log(f"Extracted {len(extracted)} tables from page {idx}")

            # Clean up the tables by converting None to empty string and stripping whitespace
            cleaned_tables = []
            for table in tables:
                cleaned_table = []
                # Extract the actual table data using extract()
                table_data = table.extract()
                for row in table_data:
                    cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
                    cleaned_table.append(cleaned_row)
                cleaned_tables.append(cleaned_table)

            return cleaned_tables

        except Exception as e:
            self._log(f"Error extracting tables: {str(e)}")
            import pdb; pdb.set_trace()

            return []

    def extract_text(self, page_number: Optional[int] = None) -> str:
        """
        Extract text from the PDF or from a specific page with layout preservation.

        Args:
            page_number: Optional page number (1-based index). If None, extracts from all pages.

        Returns:
            A string containing the extracted text with preserved layout.
        """
        try:
            self._log(f"Starting text extraction. Page number: {page_number}, Total pages: {len(self.pdf.pages)}")

            if page_number is not None:
                if 1 <= page_number <= len(self.pdf.pages):
                    page = self.pdf.pages[page_number - 1]
                    # Extract text lines with character information
                    text_lines = page.extract_text_lines(layout=False, strip=True, return_chars=True)

                    if text_lines:
                        # Join the text lines, preserving line breaks
                        text = '\n'.join(line['text'] for line in text_lines)
                        self._log(f"Successfully extracted text, length: {len(text)}")
                    else:
                        self._log("No text could be extracted from page")
                        text = ""

                    return text
                else:
                    raise ValueError(f"Page number {page_number} is out of range")
            else:
                text_parts = []
                for idx, page in enumerate(self.pdf.pages, 1):
                    self._log(f"Processing page {idx}")
                    # Extract text lines with character information
                    text_lines = page.extract_text_lines(layout=False, strip=True, return_chars=True)

                    if text_lines:
                        # Join the text lines, preserving line breaks
                        text = '\n'.join(line['text'] for line in text_lines)
                        text_parts.append(text)
                        self._log(f"Added text from page {idx}, length: {len(text)}")
                    else:
                        self._log(f"No text could be extracted from page {idx}")

                final_text = "\n\n".join(text_parts)
                self._log(f"Final combined text length: {len(final_text)}")
                return final_text

        except Exception as e:
            self._log(f"Error extracting text: {str(e)}")
            return str(e)

    def extract_all_pages(self, rules: list['DataRule']) -> list[Dict[str, Any]]:
        """Extract data from all pages of the PDF."""
        results = []
        self._log(f"Processing {len(self.pdf.pages)} pages")

        for page_num, page in enumerate(self.pdf.pages, 1):
            self._log(f"Processing page {page_num}")
            page_result = self.extract_data(rules)
            if page_result:
                results.append(page_result)

        return results
