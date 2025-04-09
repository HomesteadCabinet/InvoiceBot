# utils.py
import base64, os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import camelot
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime
from decimal import Decimal
import pytz
import logging
import pandas as pd
import re
import fitz
from PIL import Image
from io import BytesIO

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

def get_module_functions(module_path):
    """
    Get a list of all function names defined in a Python module.

    Args:
        module_path (str): Path to the Python module

    Returns:
        list: List of function names
    """
    import importlib.util
    import inspect

    # Get the module name from the file path
    module_name = os.path.splitext(os.path.basename(module_path))[0]

    # Load the module
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get all functions
    functions = []
    for name, obj in inspect.getmembers(module):
        if inspect.isfunction(obj) and obj.__module__ == module_name:
            # Use obj.name if it exists, otherwise use name
            functions.append({'method': name, 'name': getattr(obj, 'name', name)})

    return functions


class DataExtractor:
    """Enhanced PDF data extraction utility with support for multiple extraction methods."""

    def __init__(self, pdf_path: str, debug: bool = False):
        """Initialize the DataExtractor with a PDF file path."""
        self.pdf_path = pdf_path
        self.debug = debug
        self.doc = fitz.open(pdf_path)
        self._log(f"Initialized DataExtractor for {pdf_path}")

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

    def _validate_text(self, text: str, rule: Dict[str, Any]) -> bool:
        """Validate extracted text against rule constraints."""
        if rule.get('required') and not text:
            self._log(f"Required field {rule.get('field_name')} is empty")
            return False

        if rule.get('validation_regex'):
            if not re.match(rule['validation_regex'], text):
                self._log(f"Validation failed for {rule.get('field_name')}: {text}")
                return False

        if rule.get('min_value') is not None:
            try:
                value = float(text)
                if value < rule['min_value']:
                    self._log(f"Value {value} below minimum {rule['min_value']}")
                    return False
            except ValueError:
                self._log(f"Could not convert {text} to float for min_value validation")
                return False

        if rule.get('max_value') is not None:
            try:
                value = float(text)
                if value > rule['max_value']:
                    self._log(f"Value {value} above maximum {rule['max_value']}")
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

    def _extract_by_keyword(self, page_number: int, rule: Dict[str, Any]) -> Optional[str]:
        """Extract text near a keyword using camelot."""
        if not rule.get('keyword'):
            return None

        try:
            # Get parsing method from table config if available
            parsing_method = rule.get('table_config', {}).get('parsing_method', 'hybrid')

            # Extract tables using camelot
            tables = camelot.read_pdf(
                self.pdf_path,
                pages=str(page_number),
                flavor=parsing_method
            )

            if not tables:
                self._log(f"Keyword '{rule.get('keyword')}' not found")
                return None

            # Search through all tables for the keyword
            for table in tables:
                df = table.df
                for _, row in df.iterrows():
                    for cell in row:
                        if rule['keyword'] in str(cell):
                            # Get the next cell in the row
                            cell_index = row[row == cell].index[0]
                            if cell_index + 1 < len(row):
                                result = str(row[cell_index + 1]).strip()
                                self._log(f"Extracted by keyword: {result}")
                                return result

            return None
        except Exception as e:
            self._log(f"Error extracting by keyword: {str(e)}")
            return None

    def _extract_by_regex(self, page_number: int, rule: Dict[str, Any]) -> Optional[str]:
        """Extract text using regex pattern with camelot."""
        if not rule.get('regex_pattern'):
            return None

        try:
            # Get parsing method from table config if available
            parsing_method = rule.get('table_config', {}).get('parsing_method', 'hybrid')

            # Extract tables using camelot
            tables = camelot.read_pdf(
                self.pdf_path,
                pages=str(page_number),
                flavor=parsing_method
            )

            if not tables:
                self._log("No tables found")
                return None

            # Search through all tables for the regex pattern
            for table in tables:
                df = table.df
                for _, row in df.iterrows():
                    for cell in row:
                        match = re.search(rule['regex_pattern'], str(cell))
                        if match:
                            result = match.group(0)
                            self._log(f"Extracted by regex: {result}")
                            return result

            return None
        except Exception as e:
            self._log(f"Error extracting by regex: {str(e)}")
            return None

    def extract_line_items(self, page_number: int = 1):
        """
        Extract line items from the PDF.
        Args:
            page_number: Page number to extract from
        Returns:
            list: List of line items
        """
        tables = self.extract_tables(page_number)
        line_items = []

        for table in tables:
            if len(table) > 1:  # Skip empty tables
                # Assume first row is header
                headers = [str(h).lower() for h in table[0]]
                for row in table[1:]:
                    if any(cell for cell in row):  # Skip empty rows
                        item = {}
                        for i, cell in enumerate(row):
                            if i < len(headers):
                                item[headers[i]] = str(cell).strip()
                        line_items.append(item)

        return line_items

    def extract_data(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract data from PDF using the provided rules."""
        extracted_data = {}
        errors = []

        # Get total number of pages
        tables = camelot.read_pdf(self.pdf_path, pages='1-end', flavor='lattice')
        total_pages = max([table.page for table in tables]) if tables else 1

        for rule in rules:
            if rule.get('data_type') == 'line_items':
                line_items_data = {
                    'header_row': None,
                    'items': []
                }
                for page_number in range(1, total_pages + 1):
                    result = self.extract_line_items(page_number)
                    if result:
                        line_items_data['items'].extend(result)
                    if not result and rule.get('required'):
                        errors.append(f"{rule.get('field_name')} could not be extracted.")
                if line_items_data['items']:
                    extracted_data[rule['field_name']] = line_items_data
                elif rule.get('required'):
                    errors.append(f"{rule.get('field_name')} could not be extracted.")
            else:
                for page_number in range(1, total_pages + 1):
                    text = None
                    # Use the appropriate extraction method based on location type
                    if rule.get('location_type') == 'keyword':
                        text = self._extract_by_keyword(page_number, rule)
                    elif rule.get('location_type') == 'regex':
                        text = self._extract_by_regex(page_number, rule)
                    elif rule.get('location_type') == 'table':
                        text = self.extract_tables(page_number)
                    elif rule.get('location_type') == 'header':
                        text = self.extract_tables(page_number)

                    if text:
                        text = self._pre_process_text(text, rule.get('pre_processing'))
                        text = self._post_process_text(text, rule.get('data_type'), rule.get('post_processing'))
                        extracted_data[rule['field_name']] = text
                        break
                if rule.get('required') and rule.get('field_name') not in extracted_data:
                    errors.append(f"{rule.get('field_name')} could not be extracted.")

        if errors:
            raise ValueError(f"Extraction failed for fields: {', '.join(errors)}")

        return extracted_data

    def extract_tables(self, page_number: Optional[int] = None):
        """
        Extract tables from the PDF using Camelot.
        Args:
            page_number: Optional page number to extract from. If None, extracts from all pages.
        Returns:
            list: List of tables, where each table is a list of rows
        """
        try:
            tables = camelot.read_pdf(self.pdf_path, pages=str(page_number) if page_number else 'all', flavor='stream')
            return [table.df.values.tolist() for table in tables]
        except Exception as e:
            if self.debug:
                print(f"Error extracting tables: {str(e)}")
            return []

    def extract_text(self, page_number: Optional[int] = None) -> str:
        """
        Extract text from the PDF.
        Args:
            page_number: Optional page number to extract from. If None, extracts from all pages.
        Returns:
            str: Extracted text
        """
        if page_number is not None:
            return self.doc[page_number - 1].get_text()
        return "\n".join([page.get_text() for page in self.doc])

    def generate_debug_image(self, page_number: int = 1):
        """
        Generate a debug image with highlighted areas.
        Args:
            page_number: Page number to generate image for
        Returns:
            str: Base64 encoded image
        """
        if not self.debug:
            return None

        page = self.doc[page_number - 1]
        pix = page.get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Convert to base64
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    def extract_all_pages(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract data from all pages of the PDF."""
        results = []

        # Get total number of pages
        tables = camelot.read_pdf(self.pdf_path, pages='1-end', flavor='lattice')
        total_pages = max([table.page for table in tables]) if tables else 1
        self._log(f"Processing {total_pages} pages")

        for page_number in range(1, total_pages + 1):
            self._log(f"Processing page {page_number}")
            page_result = self.extract_data(rules)
            if page_result:
                results.append(page_result)

        return results
