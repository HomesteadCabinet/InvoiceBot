from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.decorators import action
from .utils import get_gmail_service, get_sheets_service, extract_invoice_data, DataExtractor
from .models import ProcessedEmail, Vendor, VendorEmail, DataRule
from .serializers import DataRuleSerializer, VendorSerializer
from django.conf import settings
import os
from datetime import datetime
import time
import re
import base64
import json

# Store temporary files with their creation time
temp_files = {}


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
            email_match = re.search(r'<(.+?)>|([^<\s]+@[^>\s]+)', from_header)
            if email_match:
                sender_email = email_match.group(1) or email_match.group(2)
                vendor_email = VendorEmail.objects.filter(email=sender_email).first()
                if vendor_email:
                    vendor_name = vendor_email.vendor.name

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
    sheets_service = get_sheets_service()
    email = service.users().messages().get(userId='me', id=email_id).execute()
    vendor_name = "Unknown"
    errors = []
    attachments = []
    invoice_data = {"attachments": []}

    # Extract sender email from headers
    from_header = next((header['value'] for header in email['payload']['headers'] if header['name'].lower() == 'from'), None)
    if from_header:
        # Extract email address from the from_header (handles both "Name <email@domain.com>" and "email@domain.com" formats)
        email_match = re.search(r'<(.+?)>|([^<\s]+@[^>\s]+)', from_header)
        if email_match:
            sender_email = email_match.group(1) or email_match.group(2)
            # Extract domain name (everything between @ and last dot)
            domain_match = re.search(r'@(.+?)\.[^.]+$', sender_email)
            if domain_match:
                vendor_name = domain_match.group(1).title()  # Capitalize first letter of each word

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

                try:
                    # Extract data from PDF
                    extracted_data = extract_invoice_data(file_path, vendor=vendor)
                    invoice_data.update(extracted_data)

                    # Save to spreadsheet
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=settings.SHEET_ID,
                        range="Sheet1!A:C",
                        valueInputOption="USER_ENTERED",
                        body={
                            'values': [[
                                invoice_data.get("invoice_number", ""),
                                invoice_data.get("date", ""),
                                invoice_data.get("total_amount", "")
                            ]]
                        }
                    ).execute()

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
                    errors.append(f"Error processing attachment {original_filename}: {str(e)}")
                    # Create or update ProcessedEmail record with error status
                    ProcessedEmail.objects.update_or_create(
                        email_id=email_id,
                        defaults={
                            'status': 'error',
                            'processed': datetime.now(),
                            'data': {'error': str(e), 'attachments': attachments}
                        }
                    )

            except Exception as e:
                errors.append(f"Error downloading attachment {part.get('filename')}: {str(e)}")

    return Response({
        'status': 'processed' if not errors else 'partial',
        'invoice': invoice_data,
        'vendor_name': vendor_name,
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


# @api_view(['POST'])
# def test_data_rule(request):
#     """
#     Test a single DataRule against a PDF file.
#     Expected request data:
#     {
#         "pdf_filename": "filename.pdf",  # Name of file that exists in /media folder
#         "data_rule": {
#             "field_name": "invoice_number",
#             "data_type": "text",
#             "location_type": "regex",
#             "regex_pattern": "Invoice\s*#?\s*([A-Z0-9-]+)",
#             "pre_processing": {"remove_spaces": true},
#             "post_processing": {"to_uppercase": true}
#         }
#     }
#     """
#     try:
#         # Get the PDF filename from the request
#         pdf_filename = request.data.get('pdf_filename')
#         if not pdf_filename:
#             return Response({'error': 'No PDF filename provided'}, status=400)

#         # Get the data rule from the request
#         data_rule_json = request.data.get('rule')
#         if not data_rule_json:
#             return Response({'error': 'No data rule provided'}, status=400)

#         # Construct the full path to the file in the media folder
#         media_dir = settings.MEDIA_ROOT
#         file_path = os.path.join(media_dir, pdf_filename)

#         # Check if the file exists
#         if not os.path.exists(file_path):
#             return Response({'error': f'File {pdf_filename} not found in media folder'}, status=404)

#         # Create a temporary DataRule object
#         temp_rule = DataRule(
#             field_name=data_rule_json.get('field_name'),
#             data_type=data_rule_json.get('data_type'),
#             location_type=data_rule_json.get('location_type'),
#             coordinates=data_rule_json.get('coordinates'),
#             keyword=data_rule_json.get('keyword'),
#             regex_pattern=data_rule_json.get('regex_pattern'),
#             table_config=data_rule_json.get('table_config'),
#             pre_processing=data_rule_json.get('pre_processing'),
#             post_processing=data_rule_json.get('post_processing')
#         )

#         # Initialize the DataExtractor
#         extractor = DataExtractor(file_path, debug=True)

#         # Extract data using the rule
#         result = None
#         for page in extractor.pdf.pages:
#             if temp_rule.data_type == 'line_items':
#                 result = extractor.extract_line_items(page, temp_rule)
#             else:
#                 # Use the appropriate extraction method based on location type
#                 if temp_rule.location_type == 'coordinates':
#                     result = extractor._extract_by_coordinates(page, temp_rule)
#                 elif temp_rule.location_type == 'keyword':
#                     result = extractor._extract_by_keyword(page, temp_rule)
#                 elif temp_rule.location_type == 'regex':
#                     result = extractor._extract_by_regex(page, temp_rule)
#                 elif temp_rule.location_type == 'table':
#                     result = extractor._extract_by_table(page, temp_rule)
#                 elif temp_rule.location_type == 'header':
#                     # For header type, we can use the table method with specific config
#                     result = extractor._extract_by_table(page, temp_rule)

#                 if result:
#                     result = extractor._pre_process_text(result, temp_rule.pre_processing)
#                     result = extractor._post_process_text(result, temp_rule.data_type, temp_rule.post_processing)
#             if result:
#                 break

#         return Response({
#             'success': True,
#             'result': result,
#             'rule_applied': {
#                 'field_name': temp_rule.field_name,
#                 'data_type': temp_rule.data_type,
#                 'location_type': temp_rule.location_type
#             }
#         })

#     except Exception as e:
#         return Response({
#             'success': False,
#             'error': str(e)
#         }, status=500)


class DataRuleViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for viewing and editing data rules.
    """
    queryset = DataRule.objects.all()
    serializer_class = DataRuleSerializer

    # def get_queryset(self):
    #     """
    #     Optionally filter by vendor_id
    #     """
    #     queryset = DataRule.objects.all()
    #     vendor_id = self.request.query_params.get('vendor_id', None)
    #     if vendor_id is not None:
    #         queryset = queryset.filter(vendor_id=vendor_id)
    #     return queryset


    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Bulk create or update data rules for a vendor.
        Expected request data:
        {
            "vendor_name": "Vendor Name",
            "rules": [
                {
                    "field_name": "invoice_number",
                    "data_type": "text",
                    ...
                },
                ...
            ]
        }
        """
        try:
            data = request.data
            vendor_name = data.get('vendor_name')
            rules = data.get('rules', [])

            if not vendor_name:
                return Response(
                    {'error': 'vendor_name is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get or create vendor
            vendor, created = Vendor.objects.get_or_create(name=vendor_name)

            import pdb; pdb.set_trace()

            # Delete existing rules for this vendor
            DataRule.objects.filter(vendor=vendor).delete()

            # Create new rules
            created_rules = []
            for rule_data in rules:
                # Set the vendor ID before validation
                rule_data['vendor'] = vendor.id
                serializer = self.get_serializer(data=rule_data)
                serializer.is_valid(raise_exception=True)
                rule = serializer.save()
                created_rules.append(rule)

            return Response({
                'message': f'Successfully created {len(created_rules)} rules',
                'rules': self.get_serializer(created_rules, many=True).data
            })

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def test(self, request, pk=None):
        """
        Test a data rule against a PDF file.
        Expected request data example:
        {
            "pdf_filename": "filename.pdf",
            "rule": {
                "field_name": "invoice_number",
                "data_type": "text",
                "location_type": "regex",
                "regex_pattern": "Invoice\s*#?\s*([A-Z0-9-]+)"
            }
        }
        """
        try:

            # Get the data rule from the request
            data_rule_json = request.data.get('rule')
            if not data_rule_json:
                return Response({'error': 'No data rule provided'}, status=400)
            rule = DataRule(
                field_name=data_rule_json.get('field_name'),
                data_type=data_rule_json.get('data_type'),
                location_type=data_rule_json.get('location_type'),
                coordinates=data_rule_json.get('coordinates'),
                keyword=data_rule_json.get('keyword'),
                regex_pattern=data_rule_json.get('regex_pattern'),
                table_config=data_rule_json.get('table_config'),
                pre_processing=data_rule_json.get('pre_processing'),
                post_processing=data_rule_json.get('post_processing')
            )

            pdf_filename = request.data.get('pdf_filename')

            if not pdf_filename:
                return Response(
                    {'error': 'pdf_filename is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Construct the full path to the file in the media folder
            media_dir = settings.MEDIA_ROOT
            file_path = os.path.join(media_dir, pdf_filename)

            # Check if the file exists
            if not os.path.exists(file_path):
                return Response(
                    {'error': f'File {pdf_filename} not found in media folder'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Initialize the DataExtractor
            extractor = DataExtractor(file_path, debug=True)

            # Extract data using the rule
            result = None
            for page in extractor.pdf.pages:
                if rule.data_type == 'line_items':
                    result = extractor.extract_line_items(page, rule)
                else:
                    # Use the appropriate extraction method based on location type
                    if rule.location_type == 'coordinates':
                        result = extractor._extract_by_coordinates(page, rule)
                    elif rule.location_type == 'keyword':
                        result = extractor._extract_by_keyword(page, rule)
                    elif rule.location_type == 'regex':
                        result = extractor._extract_by_regex(page, rule)
                    elif rule.location_type == 'table':
                        result = extractor._extract_by_table(page, rule)
                    elif rule.location_type == 'header':
                        result = extractor._extract_by_table(page, rule)

                    if result:
                        result = extractor._pre_process_text(result, rule.pre_processing)
                        result = extractor._post_process_text(result, rule.data_type, rule.post_processing)
                if result:
                    break

            return Response({
                'success': True,
                'result': result,
                'rule_applied': {
                    'field_name': rule.field_name,
                    'data_type': rule.data_type,
                    'location_type': rule.location_type
                }
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

    def get_queryset(self):
        """
        Optionally filter by name
        """
        queryset = Vendor.objects.all()
        name = self.request.query_params.get('name', None)
        if name is not None:
            queryset = queryset.filter(name__icontains=name)
        return queryset

    @action(detail=True, methods=['get'])
    def data_rules(self, request, pk=None):
        """
        Get all data rules for a specific vendor
        """
        vendor = self.get_object()
        data_rules = vendor.data_rules.all()
        serializer = DataRuleSerializer(data_rules, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def emails(self, request, pk=None):
        """
        Get all emails associated with a specific vendor
        """
        vendor = self.get_object()
        emails = vendor.emails.all()
        return Response([{'email': email.email, 'is_primary': email.is_primary} for email in emails])
