from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.decorators import action
from .utils import get_gmail_service, get_sheets_service, DataExtractor, get_module_functions
from .models import ProcessedEmail, Vendor, VendorEmail
from .serializers import VendorSerializer
from django.conf import settings
import os
from datetime import datetime
import time
import re
import base64
import json

# Store temporary files with their creation time
temp_files = {}

# List of email domains that require special handling (extracting name before email)
SPECIAL_EMAIL_DOMAINS = [
    'notification.intuit.com',
    'billtrust.com',
    'live.com',
    'outlook.com',
    'gmail.com',
    'yahoo.com',
    'hotmail.com',
    'msn.com',
]


def cleanup_temp_files():
    """Clean up temporary files older than 5 minutes"""
    current_time = time.time()
    for file_path, creation_time in list(temp_files.items()):
        if current_time - creation_time > 300:  # 5 minutes
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                del temp_files[file_path]
            except Exception as e:
                print(f"Error cleaning up file {file_path}: {e}")


def write_to_spreadsheet(invoice_data: dict, vendor: Vendor = None) -> None:
    """
    Write invoice data to Google Spreadsheet.

    Args:
        invoice_data (dict): Dictionary containing invoice data
        vendor (Vendor, optional): Vendor object if available

    Raises:
        Exception: If there's an error writing to the spreadsheet
    """
    try:
        sheets_service = get_sheets_service()

        # Get column mappings from vendor
        column_mappings = vendor.spreadsheet_column_mapping if vendor else {}

        # Create a row with empty values for all columns up to the highest mapped column
        max_col = 'A'
        for col in column_mappings.values():
            if col > max_col:
                max_col = col

        # Create a list with empty strings up to the max column
        row_data = [''] * (ord(max_col) - ord('A') + 1)

        # Fill in the data based on column mappings
        for field_name, col in column_mappings.items():
            if field_name in invoice_data:
                col_index = ord(col) - ord('A')
                row_data[col_index] = invoice_data.get(field_name, '')

        # Add vendor name and timestamp at the end if not mapped
        if vendor and 'vendor_name' not in column_mappings:
            row_data.append(vendor.name)
        if 'timestamp' not in column_mappings:
            row_data.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Write to spreadsheet
        sheets_service.spreadsheets().values().append(
            spreadsheetId=settings.SHEET_ID,
            range=f"Sheet1!A:{chr(ord('A') + len(row_data) - 1)}",
            valueInputOption="USER_ENTERED",
            body={'values': [row_data]}
        ).execute()
    except Exception as e:
        raise Exception(f"Failed to write to spreadsheet: {str(e)}")


@api_view(['GET'])
def list_invoice_emails(request):
    service = get_gmail_service()
    page_token = request.GET.get('pageToken')
    max_results = int(request.GET.get('maxResults', 100))  # Default to 100 if not specified

    # Get messages with pagination
    results = service.users().messages().list(
        userId='me',
        q='has:attachment invoice',
        maxResults=max_results,
        pageToken=page_token
    ).execute()

    messages = results.get('messages', [])
    next_page_token = results.get('nextPageToken')
    emails = []

    # Check if we're on the first page and have more than 12 records
    if not page_token and len(messages) > max_results:
        return Response({'error': f'Too many records. Maximum allowed is {max_results}.'}, status=400)

    for msg in messages:
        email = service.users().messages().get(userId='me', id=msg['id']).execute()
        # Count attachments
        attachment_count = 0
        if 'payload' in email and 'parts' in email['payload']:
            attachment_count = sum(1 for part in email['payload']['parts'] if part.get('filename'))

        # Extract 'from' field from headers
        from_header = next((header['value'] for header in email['payload']['headers'] if header['name'].lower() == 'from'), None)
        date_header = next((header['value'] for header in email['payload']['headers'] if header['name'].lower() == 'date'), None)

        # Try to find matching vendor based on sender email
        vendor_name = None
        if from_header:
            # Extract email address from the from_header (handles both "Name <email@domain.com>" and "email@domain.com" formats)
            email_match = re.search(r'<(.+?)>|([^<\s]+@[^>\s]+)', from_header)
            if email_match:
                sender_email = email_match.group(1) or email_match.group(2)

                # Special handling for emails from specific domains
                if any(sender_email.endswith(f'@{domain}') for domain in SPECIAL_EMAIL_DOMAINS):
                    # Extract the name before the email address
                    name_match = re.search(r'^(.+?)\s*<', from_header)
                    if name_match:
                        vendor_name = name_match.group(1).strip()
                    else:
                        # Fallback to domain-based name if no name found
                        domain_match = re.search(r'@(.+?)\.[^.]+$', sender_email)
                        vendor_name = domain_match.group(1).title() if domain_match else "Unknown"
                else:
                    # Original domain-based name extraction for other emails
                    domain_match = re.search(r'@(.+?)\.[^.]+$', sender_email)
                    vendor_name = domain_match.group(1).title() if domain_match else "Unknown"

                try:
                    # Create or update vendor
                    vendor, created = Vendor.objects.update_or_create(
                        name=vendor_name,
                        defaults={
                            'invoice_type': 'pdf'  # Default to PDF, can be updated later
                        }
                    )

                    # Create or update vendor email
                    VendorEmail.objects.update_or_create(
                        email=sender_email,
                        defaults={
                            'vendor': vendor,
                            'is_primary': True
                        }
                    )
                except Exception as e:
                    errors.append(f"Error creating/updating vendor: {str(e)}")

        obj = ProcessedEmail.objects.filter(email_id=msg['id']).first()
        if obj:
            status = obj.status
        else:
            status = None

        emails.append({
            'id': msg['id'],
            'snippet': email['snippet'],
            'attachment_count': attachment_count,
            'from': from_header,
            'date': date_header,
            'message_data': obj.data if obj else None,
            'status': status,
            'vendor_name': vendor_name
        })

    return Response({
        'emails': emails,
        'nextPageToken': next_page_token
    })


@api_view(['POST'])
def process_invoice_email(request):
    email_id = request.data.get('email_id')
    service = get_gmail_service()
    email = service.users().messages().get(userId='me', id=email_id).execute()
    vendor_name = "Unknown"
    errors = []
    attachments = []
    invoice_data = {"attachments": [], "tables": [], "text": ""}

    # Extract sender email from headers
    from_header = next((header['value'] for header in email['payload']['headers'] if header['name'].lower() == 'from'), None)
    if from_header:
        # Extract email address from the from_header (handles both "Name <email@domain.com>" and "email@domain.com" formats)
        email_match = re.search(r'<(.+?)>|([^<\s]+@[^>\s]+)', from_header)
        if email_match:
            sender_email = email_match.group(1) or email_match.group(2)

            # Special handling for emails from specific domains
            if any(sender_email.endswith(f'@{domain}') for domain in SPECIAL_EMAIL_DOMAINS):
                # Extract the name before the email address
                name_match = re.search(r'^(.+?)\s*<', from_header)
                if name_match:
                    vendor_name = name_match.group(1).strip()
                else:
                    # Fallback to domain-based name if no name found
                    domain_match = re.search(r'@(.+?)\.[^.]+$', sender_email)
                    vendor_name = domain_match.group(1).title() if domain_match else "Unknown"
            else:
                # Original domain-based name extraction for other emails
                domain_match = re.search(r'@(.+?)\.[^.]+$', sender_email)
                vendor_name = domain_match.group(1).title() if domain_match else "Unknown"

            try:
                # Create or update vendor
                vendor, created = Vendor.objects.update_or_create(
                    name=vendor_name,
                    defaults={
                        'invoice_type': 'pdf'  # Default to PDF, can be updated later
                    }
                )

                # Create or update vendor email
                VendorEmail.objects.update_or_create(
                    email=sender_email,
                    defaults={
                        'vendor': vendor,
                        'is_primary': True
                    }
                )
            except Exception as e:
                errors.append(f"Error creating/updating vendor: {str(e)}")

    # Create media directory if it doesn't exist
    media_dir = settings.MEDIA_ROOT
    os.makedirs(media_dir, exist_ok=True)

    for part in email['payload']['parts']:
        if part.get('filename'):
            try:
                attachment = service.users().messages().attachments().get(
                    userId='me', messageId=email_id, id=part['body']['attachmentId']).execute()

                # Decode the attachment data
                file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))

                # Create a unique filename using email_id and original filename
                original_filename = part['filename']
                file_extension = os.path.splitext(original_filename)[1]
                # Sanitize the filename by replacing spaces and special characters
                safe_filename = re.sub(r'[^a-zA-Z0-9.-]', '_', original_filename)
                unique_filename = f"{email_id}_{safe_filename}"
                file_path = os.path.join(media_dir, unique_filename)

                # Save the file
                with open(file_path, 'wb') as f:
                    f.write(file_data)

                # Get the file URL - properly encode the filename
                file_url = request.build_absolute_uri(f'/media/{unique_filename}')

                attachment_info = {
                    'filename': unique_filename,
                    'mimeType': part['mimeType'],
                    'size': part['body'].get('size', 0),
                    'url': file_url
                }
                attachments.append(attachment_info)
                invoice_data["attachments"] = attachments

                # Extract data from PDF using vendor-specific rules if available
                extractor = DataExtractor(file_path, debug=True)

                # Extract all tables from the PDF and add to invoice_data
                # all_tables = []
                # try:
                #     # tables = extractor.extract_tables()
                #     # text = extractor.extract_text()

                #     # Get table areas and parsing method from vendor rules if available
                #     table_areas = None
                #     parsing_method = 'hybrid'  # Default parsing method

                #     # image = extractor.generate_debug_image(table_areas=table_areas, parsing_method=parsing_method)
                #     print(f"Extracted text length: {len(text) if text else 0}")  # Debug print
                #     # invoice_data['tables'] = tables
                #     # invoice_data['text'] = text
                #     # invoice_data['image'] = image
                # except Exception as e:
                #     print(f"Error during extraction: {str(e)}")  # Debug print
                #     errors.append(f"Error extracting data: {str(e)}")

                # If vendor rules exist, also extract data using those rules
                if vendor:
                    extracted_data = extractor.extract_data([])
                    invoice_data['vendor_extracted_data'] = extracted_data

                # Create or update ProcessedEmail record
                ProcessedEmail.objects.update_or_create(
                    email_id=email_id,
                    defaults={
                        'status': 'processed',
                        'processed': datetime.now(),
                        'data': invoice_data
                    }
                )

            except Exception as e:
                errors.append(f"Error downloading attachment {part.get('filename')}: {str(e)}")

    return Response({
        'status': 'processed' if not errors else 'partial',
        'invoice': invoice_data,
        'vendor': VendorSerializer(vendor).data if vendor else None,
        'errors': errors
    })


@api_view(['GET'])
def get_email_attachments(request, email_id):
    service = get_gmail_service()
    try:
        # Get the email message
        email = service.users().messages().get(userId='me', id=email_id).execute()

        attachments = []
        for part in email['payload']['parts']:
            if part.get('filename'):
                attachment = service.users().messages().attachments().get(
                    userId='me', messageId=email_id, id=part['body']['attachmentId']).execute()
                # Import base64 at the top of the file

                # Decode the attachment data
                file_data = base64.urlsafe_b64decode(
                    attachment['data'].encode('UTF-8')
                )

                # Create media directory if it doesn't exist
                media_dir = settings.MEDIA_ROOT
                os.makedirs(media_dir, exist_ok=True)

                # Create a unique filename using email_id and original filename
                original_filename = part['filename']
                file_extension = os.path.splitext(original_filename)[1]
                # Sanitize the filename by replacing spaces and special characters
                safe_filename = re.sub(r'[^a-zA-Z0-9.-]', '_', original_filename)
                unique_filename = f"{email_id}_{safe_filename}"
                file_path = os.path.join(media_dir, unique_filename)

                # Save the file
                with open(file_path, 'wb') as f:
                    f.write(file_data)

                # Get the file URL - properly encode the filename
                file_url = request.build_absolute_uri(f'/media/{unique_filename}')

                attachments.append({
                    'filename': unique_filename,
                    'mimeType': part['mimeType'],
                    'size': part['body'].get('size', 0),
                    'url': file_url
                })

        return Response({
            'attachments': attachments,
            'message': f'Found {len(attachments)} attachments'
        })

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=500)


@api_view(['POST'])
def cleanup_attachment(request):
    """Endpoint to clean up a specific attachment file"""
    file_path = request.data.get('file_path')
    if file_path and file_path in temp_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            del temp_files[file_path]
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=500)
    return Response({'error': 'File not found'}, status=404)


@api_view(['POST'])
def test_parser(request):
    """
    Test a data rule against a PDF file.
    """
    parser_data = request.data.get('parser')
    if not parser_data:
        return Response({'error': 'Parser data is required'}, status=status.HTTP_400_BAD_REQUEST)

    parser_method = parser_data.get('method')
    if not parser_method:
        return Response({'error': 'Parser method is required'}, status=status.HTTP_400_BAD_REQUEST)

    pdf_filename = request.data.get('pdf_filename')
    if not pdf_filename:
        return Response({'error': 'pdf_filename is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Construct the full path to the file in the media folder
    media_dir = settings.MEDIA_ROOT
    file_path = os.path.join(media_dir, pdf_filename)

    # Check if the file exists
    if not os.path.exists(file_path):
        return Response(
            {'error': f'File {pdf_filename} not found in media folder'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        # Import the parser function dynamically
        from . import parsers
        parser_func = getattr(parsers, parser_method, None)

        if not parser_func:
            return Response(
                {'error': f'Parser method {parser_method} not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Run the parser
        result = parser_func(file_path)

        # Convert pandas DataFrame to dict if needed
        if hasattr(result, 'to_dict'):
            result = result.to_dict('records')

        return Response({
            'success': True,
            'result': result
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class VendorViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for viewing and editing vendors.
    """
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer

    def update(self, request, *args, **kwargs):
        """
        Update a vendor.
        """
        obj = self.get_object()
        return super().update(request, *args, **kwargs)

    def get_queryset(self):
        """
        Optionally filter by name
        """
        queryset = Vendor.objects.all()
        name = self.request.query_params.get('name', None)
        if name is not None:
            queryset = queryset.filter(name__icontains=name)
        return queryset

    @action(detail=False, methods=['get'])
    def get_invoice_parsers(self, request):
        """
        Get a list of available parser methods from parsers.py
        """
        try:
            parsers_path = os.path.join(os.path.dirname(__file__), 'parsers.py')
            available_parsers = get_module_functions(parsers_path)
            return Response({
                'available_parsers': available_parsers,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def emails(self, request, pk=None):
        """
        Get all emails associated with a specific vendor
        """
        vendor = self.get_object()
        emails = vendor.emails.all()
        return Response([{'email': email.email, 'is_primary': email.is_primary} for email in emails])
