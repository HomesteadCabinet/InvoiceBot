from rest_framework.decorators import api_view
from rest_framework.response import Response
from .utils import get_gmail_service, get_sheets_service, extract_invoice_data
from .models import ProcessedEmail, Vendor, VendorEmail
from django.conf import settings
import os
from datetime import datetime
import time
import re
import base64

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
    max_results = 100  # Number of results per page

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

    # Create media directory if it doesn't exist
    media_dir = settings.MEDIA_ROOT
    os.makedirs(media_dir, exist_ok=True)

    invoice_data = {}
    attachments = []

    for part in email['payload']['parts']:
        if part.get('filename'):
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
                'filename': original_filename,
                'mimeType': part['mimeType'],
                'size': part['body'].get('size', 0),
                'url': file_url
            }
            attachments.append(attachment_info)

            try:
                # Extract data from PDF
                extracted_data = extract_invoice_data(file_path)
                invoice_data = {
                    **extracted_data,
                    'attachments': attachments
                }

                # Save to spreadsheet
                sheets_service.spreadsheets().values().append(
                    spreadsheetId=settings.SHEET_ID,
                    range="Sheet1!A:C",
                    valueInputOption="USER_ENTERED",
                    body={
                        'values': [[
                            invoice_data["invoice_number"],
                            invoice_data["date"],
                            invoice_data["total_amount"]
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
                # Create or update ProcessedEmail record with error status
                ProcessedEmail.objects.update_or_create(
                    email_id=email_id,
                    defaults={
                        'status': 'error',
                        'processed': datetime.now(),
                        'data': {'error': str(e)}
                    }
                )
                return Response({'status': 'error', 'message': str(e)}, status=500)

    return Response({
        'status': 'processed',
        'invoice': invoice_data,
        'vendor_name': vendor_name,
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
                    'filename': original_filename,
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
