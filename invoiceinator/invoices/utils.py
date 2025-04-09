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
        self.pdf = None
        self.debug = debug
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

    def _extract_by_keyword(self, page_number: int, rule: 'DataRule') -> Optional[str]:
        """Extract text near a keyword using camelot."""
        if not rule.keyword:
            return None

        try:
            # Get parsing method from table config if available
            parsing_method = rule.table_config.get('parsing_method', 'hybrid') if hasattr(rule, 'table_config') else 'hybrid'

            # Extract tables using camelot
            tables = camelot.read_pdf(
                self.pdf_path,
                pages=str(page_number),
                flavor=parsing_method
            )

            if not tables:
                self._log(f"Keyword '{rule.keyword}' not found")
                return None

            # Search through all tables for the keyword
            for table in tables:
                df = table.df
                for _, row in df.iterrows():
                    for cell in row:
                        if rule.keyword in str(cell):
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

    def _extract_by_regex(self, page_number: int, rule: 'DataRule') -> Optional[str]:
        """Extract text using regex pattern with camelot."""
        if not rule.regex_pattern:
            return None

        try:
            # Get parsing method from table config if available
            parsing_method = rule.table_config.get('parsing_method', 'hybrid') if hasattr(rule, 'table_config') else 'hybrid'

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
                        match = re.search(rule.regex_pattern, str(cell))
                        if match:
                            result = match.group(0)
                            self._log(f"Extracted by regex: {result}")
                            return result

            return None
        except Exception as e:
            self._log(f"Error extracting by regex: {str(e)}")
            return None

    def extract_line_items(self, page_number: int, rule: 'DataRule') -> Dict[str, Any]:
        """Extract line items from a page using camelot."""
        items = []
        header_row = None

        if rule.location_type == 'table':
            # Get parsing method from config, default to 'hybrid' if not specified
            parsing_method = rule.table_config.get('parsing_method', 'hybrid') if hasattr(rule, 'table_config') else 'hybrid'

            table_areas = None
            if hasattr(rule, 'bbox'):
                bbox = rule.bbox
                # Convert bbox to camelot format: "x1,y1,x2,y2" where (x1,y1) is top-left and (x2,y2) is bottom-right
                x1 = bbox['x']
                y1 = bbox['y']
                x2 = x1 + bbox['width']
                y2 = y1 + bbox['height']
                table_areas = [f"{x1},{y1},{x2},{y2}"]

            # Extract tables using camelot
            tables = camelot.read_pdf(
                self.pdf_path,
                pages=str(page_number),
                flavor=parsing_method,
                table_areas=table_areas
            )

            if not tables:
                self._log("No tables found on page")
                return {'header_row': None, 'items': []}

            for table in tables:
                df = table.df

                # Find header row based on config or keyword
                header_row_idx = None
                item_columns = rule.table_config.get('item_columns', {})
                header_keyword = rule.table_config.get('header_text', 'code').lower()

                # Find header row
                for idx, row in df.iterrows():
                    if any(cell and header_keyword in str(cell).lower() for cell in row):
                        header_row_idx = idx
                        header_row = row.tolist()  # Store the header row

                        # Auto-detect item_columns if not explicitly provided
                        if not item_columns:
                            self._log(f"Auto-detecting item columns from header: {row.tolist()}")
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
                                    item_columns["total_price"] = col_idx
                        else:
                            # Convert string column names to indices if needed
                            for key, value in list(item_columns.items()):
                                if isinstance(value, str):
                                    # Find the column index that matches the value
                                    for col_idx, col in enumerate(row):
                                        if str(col).strip().lower() == value.lower():
                                            item_columns[key] = col_idx
                                            break
                        break

                if header_row_idx is None or not item_columns:
                    continue  # No valid header found or failed to map columns

                # Process rows after header
                start_row = header_row_idx + rule.table_config.get('start_row_after_header', 1)
                for _, row in df.iloc[start_row:].iterrows():
                    if row.isna().all():  # Skip empty rows
                        continue

                    item = {}
                    # Initialize all columns with null
                    for key in item_columns.keys():
                        item[key] = None

                    for key, col_idx in item_columns.items():
                        # Ensure col_idx is an integer
                        if isinstance(col_idx, str):
                            # Try to find the column index by name
                            for idx, col in enumerate(header_row):
                                if str(col).strip().lower() == col_idx.lower():
                                    col_idx = idx
                                    break
                            else:
                                continue  # Skip if column not found

                        if isinstance(col_idx, int) and col_idx < len(row):
                            value = row.iloc[col_idx]
                            item[key] = str(value).strip() if pd.notna(value) else None
                    if any(v is not None for v in item.values()):  # Only add if at least one value is not null
                        items.append(item)

        elif rule.location_type == 'regex':
            # Get parsing method from table config if available
            parsing_method = rule.table_config.get('parsing_method', 'hybrid') if hasattr(rule, 'table_config') else 'hybrid'

            # Extract tables using camelot
            tables = camelot.read_pdf(
                self.pdf_path,
                pages=str(page_number),
                flavor=parsing_method
            )

            if not tables:
                self._log("No tables found")
                return {'header_row': None, 'items': []}

            pattern = re.compile(rule.regex_pattern)
            for table in tables:
                df = table.df
                for _, row in df.iterrows():
                    for cell in row:
                        matches = pattern.findall(str(cell))
                        for match in matches:
                            if isinstance(match, tuple):
                                items.append({
                                    'quantity': match[0],
                                    'description': match[1],
                                    'unit_price': match[2],
                                    'amount': match[3],
                                })
                            else:
                                items.append({
                                    'description': match
                                })

        return {
            'header_row': header_row,
            'items': items
        }

    def extract_data(self, rules: list['DataRule']) -> Dict[str, Any]:
        """Extract data from PDF using the provided rules."""
        extracted_data = {}
        errors = []

        # Get total number of pages
        tables = camelot.read_pdf(self.pdf_path, pages='1-end', flavor='lattice')
        total_pages = max([table.page for table in tables]) if tables else 1

        for rule in rules:
            if rule.data_type == 'line_items':
                line_items_data = {
                    'header_row': None,
                    'items': []
                }
                for page_number in range(1, total_pages + 1):
                    result = self.extract_line_items(page_number, rule)
                    if result['header_row'] and not line_items_data['header_row']:
                        line_items_data['header_row'] = result['header_row']
                    if result['items']:
                        line_items_data['items'].extend(result['items'])
                if line_items_data['items']:
                    extracted_data[rule.field_name] = line_items_data
                elif rule.required:
                    errors.append(f"{rule.field_name} could not be extracted.")
            else:
                for page_number in range(1, total_pages + 1):
                    text = None
                    # Use the appropriate extraction method based on location type
                    if rule.location_type == 'keyword':
                        text = self._extract_by_keyword(page_number, rule)
                    elif rule.location_type == 'regex':
                        text = self._extract_by_regex(page_number, rule)
                    elif rule.location_type == 'table':
                        text = self.extract_tables(page_number, rule)
                    elif rule.location_type == 'header':
                        text = self.extract_tables(page_number, rule)

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

    def extract_tables(self, page_number: Optional[int] = None, rule: Optional['DataRule'] = None):
        """
        Extract tables from the PDF using camelot-py.

        Args:
            page_number: Optional page number (1-based index). If None, extracts from all pages.
            rule: Optional DataRule for targeted field extraction. If provided, returns a single value.

        Returns:
            If rule is None: List of tables, where each table is a list of rows, and each row is a list of cell values.
            If rule is provided: Single extracted value based on the rule configuration.
        """
        try:
            # Get parsing method from table config if available
            parsing_method = rule.table_config.get('parsing_method', 'hybrid') if rule and hasattr(rule, 'table_config') else 'hybrid'

            # Prepare table_areas from bbox if provided
            table_areas = None
            if rule and rule.table_config and rule.table_config.get('bbox'):
                bbox = rule.table_config['bbox']
                # Convert bbox to camelot format: "x1,y1,x2,y2" where (x1,y1) is top-left and (x2,y2) is bottom-right
                x1 = bbox['x']
                y1 = bbox['y']
                x2 = x1 + bbox['width']
                y2 = y1 + bbox['height']
                table_areas = [f"{x1},{y1},{x2},{y2}"]

            if page_number is not None:
                # Extract tables using camelot with specified or default flavor
                extracted = camelot.read_pdf(
                    self.pdf_path,
                    pages=str(page_number),
                    flavor=parsing_method,
                    table_areas=table_areas
                )
                if extracted:
                    self._log(f"Extracted {len(extracted)} tables from page {page_number}")
                else:
                    self._log("No tables found on page")
                    return [] if not rule else None
            else:
                extracted = camelot.read_pdf(
                    self.pdf_path,
                    pages='1-end',
                    flavor=parsing_method,
                    table_areas=table_areas
                )
                if extracted:
                    self._log(f"Extracted {len(extracted)} tables from all pages")
                else:
                    self._log("No tables found")
                    return [] if not rule else None

            # If a rule is provided, extract specific field value
            if rule and rule.table_config:
                for table in extracted:
                    df = table.df

                    # Find the correct row/column based on header
                    if rule.table_config.get('header_text'):
                        for row_idx, row in df.iterrows():
                            if rule.table_config['header_text'] in row.values:
                                if rule.table_config.get('col_index') is not None:
                                    result = df.iloc[row_idx + rule.table_config.get('row_index', 1), rule.table_config['col_index']]
                                    self._log(f"Extracted from table by header: {result}")
                                    return str(result) if pd.notna(result) else None
                                break
                    else:
                        # Direct row/column access
                        if rule.table_config.get('row_index') is not None and rule.table_config.get('col_index') is not None:
                            result = df.iloc[rule.table_config['row_index'], rule.table_config['col_index']]
                            self._log(f"Extracted from table by index: {result}")
                            return str(result) if pd.notna(result) else None
                return None

            # If no rule provided, return all tables
            cleaned_tables = []
            for table in extracted:
                df = table.df
                cleaned_table = []
                for _, row in df.iterrows():
                    cleaned_row = [str(cell).strip() if pd.notna(cell) else "" for cell in row]
                    cleaned_table.append(cleaned_row)
                cleaned_tables.append(cleaned_table)

            return cleaned_tables

        except Exception as e:
            self._log(f"Error extracting tables: {str(e)}")
            return [] if not rule else None

    def extract_text(self, page_number: Optional[int] = None) -> str:
        """
        Extract text from the PDF using camelot.

        Args:
            page_number: Optional page number (1-based index). If None, extracts from all pages.

        Returns:
            A string containing the extracted text.
        """
        try:
            self._log(f"Starting text extraction. Page number: {page_number}")

            if page_number is not None:
                # Extract tables using camelot
                tables = camelot.read_pdf(
                    self.pdf_path,
                    pages=str(page_number),
                    flavor='hybrid'
                )

                if not tables:
                    self._log("No text could be extracted from page")
                    return ""

                # Combine all table text
                text_parts = []
                for table in tables:
                    df = table.df
                    for _, row in df.iterrows():
                        row_text = ' '.join(str(cell).strip() for cell in row if pd.notna(cell))
                        if row_text:
                            text_parts.append(row_text)

                text = '\n'.join(text_parts)
                self._log(f"Successfully extracted text, length: {len(text)}")
                return text

            else:
                # Extract tables from all pages
                tables = camelot.read_pdf(
                    self.pdf_path,
                    pages='1-end',
                    flavor='hybrid'
                )

                if not tables:
                    self._log("No text could be extracted")
                    return ""

                # Combine all table text
                text_parts = []
                for table in tables:
                    df = table.df
                    for _, row in df.iterrows():
                        row_text = ' '.join(str(cell).strip() for cell in row if pd.notna(cell))
                        if row_text:
                            text_parts.append(row_text)

                text = '\n'.join(text_parts)
                self._log(f"Successfully extracted text from all pages, length: {len(text)}")
                return text

        except Exception as e:
            self._log(f"Error extracting text: {str(e)}")
            return ""

    def generate_debug_image(self, page_number: int = 1, output_path: str = None, dpi: int = 210, table_areas: List[str] = None, parsing_method: str = 'hybrid') -> str:
        """
        Generate a PNG image of the extracted tables for debugging purposes.

        Args:
            page_number: Page number (1-based index) to extract tables from
            output_path: Optional path to save the PNG image. If None, generates a default path.
            dpi: Resolution of the output image in dots per inch.
            table_areas: Optional list of table areas in format "x1,y1,x2,y2" where (x1,y1) is top-left and (x2,y2) is bottom-right
            parsing_method: Method to use for table parsing ('lattice', 'stream', or 'hybrid'). Defaults to 'hybrid'.

        Returns:
            Path to the generated PNG image
        """
        try:
            # Extract tables using camelot
            tables = camelot.read_pdf(
                self.pdf_path,
                pages=str(page_number),
                flavor=parsing_method,
                table_areas=table_areas
            )

            if not tables:
                self._log("No tables found to generate image")
                return None

            # Generate default output path if not provided
            if output_path is None:
                base_name = os.path.splitext(os.path.basename(self.pdf_path))[0]
                output_path = f"media/{base_name}_page{page_number}_tables.png"

            # Plot and save the image
            camelot.plot(tables[0], kind='grid').savefig(output_path, dpi=dpi, bbox_inches='tight')
            self._log(f"Generated table image: {output_path} with DPI={dpi}, tight bounding box")
            return output_path

        except Exception as e:
            self._log(f"Error generating table image: {str(e)}")
            return None

    def extract_all_pages(self, rules: list['DataRule']) -> list[Dict[str, Any]]:
        """Extract data from all pages of the PDF."""
        results = []

        # Get parsing method from first rule if available
        parsing_method = 'hybrid'
        if rules and hasattr(rules[0], 'table_config'):
            parsing_method = rules[0].table_config.get('parsing_method', 'hybrid')

        # Get total number of pages
        tables = camelot.read_pdf(self.pdf_path, pages='1-end', flavor=parsing_method)
        total_pages = max([table.page for table in tables]) if tables else 1
        self._log(f"Processing {total_pages} pages")

        for page_number in range(1, total_pages + 1):
            self._log(f"Processing page {page_number}")
            page_result = self.extract_data(rules)
            if page_result:
                results.append(page_result)

        return results
