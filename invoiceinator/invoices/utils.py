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

GMAIL_USER_ID = 'me'
SHEET_ID = '13_nri-gfP9A8w69TXKujR0z_ma4Oqy4zywOJXeJZOUY'

def get_gmail_service():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    return build('gmail', 'v1', credentials=creds)

def get_sheets_service():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    return build('sheets', 'v4', credentials=creds)

def extract_invoice_data(pdf_path):
    print(f"\nProcessing PDF: {pdf_path}")

    with pdfplumber.open(pdf_path) as pdf:
        print(f"Number of pages in PDF: {len(pdf.pages)}")
        text = ''
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            print(f"\nPage {i+1} text length: {len(page_text) if page_text else 0} characters")
            if page_text:
                print("First 200 characters of page:")
                print(page_text[:200])
            text += page_text

    print(f"\nTotal extracted text length: {len(text)} characters")
    print("First 500 characters of full text:")
    print(text[:500])

    # More flexible patterns that handle various formats
    patterns = {
        'invoice_number': [
            r'Invoice\s*(?:Number|No|#)?[: ]*([A-Z0-9-]+)',
            r'INV[- ]?(\d+)',
            r'Invoice\s*[: ]*([A-Z0-9-]+)',
        ],
        'date': [
            r'Date[: ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'Invoice\s*Date[: ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',  # Fallback to first date found
        ],
        'total_amount': [
            r'Total\s*(?:Amount)?[: ]*[\$£]?([\d,]+\.\d{2})',
            r'Amount\s*Due[: ]*[\$£]?([\d,]+\.\d{2})',
            r'[\$£]?([\d,]+\.\d{2})',  # Fallback to last amount found
        ]
    }

    extracted_data = {}
    errors = []

    print("\nAttempting to match patterns:")
    for field, field_patterns in patterns.items():
        print(f"\nTrying to find {field}:")
        value = None
        for i, pattern in enumerate(field_patterns):
            print(f"  Pattern {i+1}: {pattern}")
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                print(f"  ✓ Found match: {value}")
                break
            else:
                print("  ✗ No match")

        if value:
            extracted_data[field] = value
        else:
            print(f"  ✗ Failed to find {field} with any pattern")
            errors.append(f"Could not find {field}")

    if errors:
        error_msg = f"Failed to extract required data: {', '.join(errors)}"
        print(f"\n❌ {error_msg}")
        raise ValueError(error_msg)

    print("\n✓ Successfully extracted all data:")
    for field, value in extracted_data.items():
        print(f"  {field}: {value}")

    return extracted_data

class DataExtractor:
    """Enhanced PDF data extraction utility with support for multiple extraction methods."""

    # Default patterns for common invoice fields
    DEFAULT_PATTERNS = {
        'invoice_number': [
            r'Invoice\s*(?:Number|No|#)?[: ]*([A-Z0-9-]+)',
            r'INV[- ]?(\d+)',
            r'Invoice\s*[: ]*([A-Z0-9-]+)',
        ],
        'date': [
            r'Date[: ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'Invoice\s*Date[: ]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',  # Fallback to first date found
        ],
        'total_amount': [
            r'Total\s*(?:Amount)?[: ]*[\$£]?([\d,]+\.\d{2})',
            r'Amount\s*Due[: ]*[\$£]?([\d,]+\.\d{2})',
            r'[\$£]?([\d,]+\.\d{2})',  # Fallback to last amount found
        ]
    }

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

            # Extract text after the keyword (up to 100 characters)
            start_pos = keyword_pos + len(rule.keyword)
            end_pos = min(start_pos + 100, len(text))
            result = text[start_pos:end_pos].strip()
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

    def extract_data(self, rules: list['DataRule']) -> Dict[str, Any]:
        """Extract data from PDF using provided rules."""
        result = {}
        errors = []

        self._log(f"Starting data extraction with {len(rules)} rules")

        for page in self.pdf.pages:
            for rule in rules:
                if rule.field_name in result:
                    continue

                # Extract text based on location type
                text = None
                if rule.location_type == 'coordinates':
                    text = self._extract_by_coordinates(page, rule)
                elif rule.location_type == 'keyword':
                    text = self._extract_by_keyword(page, rule)
                elif rule.location_type == 'regex':
                    text = self._extract_by_regex(page, rule)
                elif rule.location_type == 'table':
                    text = self._extract_by_table(page, rule)

                if text:
                    # Apply pre-processing
                    text = self._pre_process_text(text, rule.pre_processing)

                    # Validate
                    if self._validate_text(text, rule):
                        # Apply post-processing
                        processed_value = self._post_process_text(text, rule.data_type, rule.post_processing)
                        result[rule.field_name] = processed_value
                    else:
                        errors.append(f"Validation failed for {rule.field_name}")
                else:
                    errors.append(f"Could not extract {rule.field_name}")

        if errors and any(rule.required for rule in rules):
            error_msg = f"Failed to extract required data: {', '.join(errors)}"
            self._log(f"❌ {error_msg}")
            raise ValueError(error_msg)

        self._log("✓ Successfully extracted all data")
        return result

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

    def extract_with_default_patterns(self) -> Dict[str, Any]:
        """Extract data using default patterns for common invoice fields."""
        self._log("Using default patterns for extraction")
        result = {}

        # Convert default patterns to DataRule-like structure
        for field, patterns in self.DEFAULT_PATTERNS.items():
            for pattern in patterns:
                try:
                    text = self.pdf.pages[0].extract_text()
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        result[field] = match.group(1)
                        self._log(f"Found {field}: {result[field]}")
                        break
                except Exception as e:
                    self._log(f"Error extracting {field}: {str(e)}")

        return result
