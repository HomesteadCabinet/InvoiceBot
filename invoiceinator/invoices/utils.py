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


def extract_invoice_data(pdf_path, vendor=None):
    """Extract data from a PDF invoice using vendor-specific data rules."""
    print(f"\nProcessing PDF: {pdf_path}")

    # Initialize DataExtractor
    extractor = DataExtractor(pdf_path, debug=True)

    # If vendor is provided, use their data rules
    if vendor:
        data_rules = vendor.data_rules.all()
        if data_rules:
            try:
                extracted_data = extractor.extract_data(data_rules)
                print("\n✓ Successfully extracted data using vendor rules:")
                for field, value in extracted_data.items():
                    print(f"  {field}: {value}")
                return extracted_data
            except ValueError as e:
                print(f"\n❌ Error extracting data: {str(e)}")
                raise

    # Fallback to default extraction if no vendor rules or extraction failed
    print("No vendor rules found or extraction failed, using default extraction")
    with pdfplumber.open(pdf_path) as pdf:
        text = ''
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text

    # Default patterns for common invoice fields
    patterns = {
        'invoice_number': [
            r'Invoice\s*(?:Number|No|#)?[: ]*([A-Z0-9-]+)',
            r'INV[- ]?(\d+)',
            r'Invoice\s*[: ]*([A-Z0-9-]+)',
        ],
        'date': [
            r'Date[: ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'Invoice\s*Date[: ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        ],
        'total_amount': [
            r'Total\s*(?:Amount)?[: ]*[\$£]?([\d,]+\.\d{2})',
            r'Amount\s*Due[: ]*[\$£]?([\d,]+\.\d{2})',
            r'[\$£]?([\d,]+\.\d{2})',
        ]
    }

    extracted_data = {}
    errors = []

    for field, field_patterns in patterns.items():
        value = None
        for pattern in field_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                break

        if value:
            extracted_data[field] = value
        else:
            errors.append(f"Could not find {field}")

    if errors:
        error_msg = f"Failed to extract required data: {', '.join(errors)}"
        print(f"\n❌ {error_msg}")
        raise ValueError(error_msg)

    print("\n✓ Successfully extracted data using default patterns:")
    for field, value in extracted_data.items():
        print(f"  {field}: {value}")

    return extracted_data

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

    def _extract_by_coordinates(self, page, rule: 'DataRule') -> Optional[str]:
        """Extract text using coordinates."""
        coords = rule.coordinates
        if not coords:
            return None

        try:
            # Extract text from the specified coordinates
            text = page.crop((coords['x'], coords['y'],
                            coords['x'] + coords['width'],
                            coords['y'] + coords['height'])).extract_text()
            self._log(f"Extracted by coordinates: {text}")
            return text
        except Exception as e:
            self._log(f"Error extracting by coordinates: {str(e)}")
            return None

    def _extract_by_keyword(self, page, rule: 'DataRule') -> Optional[str]:
        """Extract text near a keyword."""
        if not rule.keyword:
            return None

        try:
            text = page.extract_text()
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
            text = page.extract_text()
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

        if rule.location_type == 'table':
            tables = page.extract_tables()
            for table in tables:
                # Find header row
                header_row_idx = None
                for idx, row in enumerate(table):
                    if rule.table_config['header_text'] in row:
                        header_row_idx = idx
                        break
                if header_row_idx is None:
                    continue

                item_columns = rule.table_config['item_columns']
                for row in table[header_row_idx + rule.table_config.get('start_row_after_header', 1):]:
                    if not row or all(not cell.strip() for cell in row if cell):
                        continue
                    item = {
                        'description': row[item_columns['description']].strip(),
                        'quantity': row[item_columns['quantity']].strip(),
                        'unit_price': row[item_columns['unit_price']].strip(),
                        'amount': row[item_columns['amount']].strip(),
                    }
                    items.append(item)
            return items

        elif rule.location_type == 'regex':
            text = page.extract_text()
            pattern = re.compile(rule.regex_pattern)
            matches = pattern.findall(text)
            for match in matches:
                items.append({
                    'quantity': match[0],
                    'description': match[1],
                    'unit_price': match[2],
                    'amount': match[3],
                })
            return items
        return items

    def extract_data(self, rules: list['DataRule']) -> Dict[str, Any]:
        extracted_data = {}
        errors = []

        for rule in rules:
            if rule.data_type == 'line_items':
                line_items = []
                for page in self.pdf.pages:
                    line_items += self.extract_line_items(page, rule)
                extracted_data[rule.field_name] = line_items
            else:
                for page in self.pdf.pages:
                    text = None
                    # Use the appropriate extraction method based on location type
                    if rule.location_type == 'coordinates':
                        text = self._extract_by_coordinates(page, rule)
                    elif rule.location_type == 'keyword':
                        text = self._extract_by_keyword(page, rule)
                    elif rule.location_type == 'regex':
                        text = self._extract_by_regex(page, rule)
                    elif rule.location_type == 'table':
                        text = self._extract_by_table(page, rule)
                    elif rule.location_type == 'header':
                        # For header type, we can use the table method with specific config
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
