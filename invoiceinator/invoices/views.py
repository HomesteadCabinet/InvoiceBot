from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.decorators import action
from .utils import get_gmail_service
from .google_oauth import (
    build_frontend_redirect,
    disconnect_credentials,
    exchange_authorization_code,
    get_authorization_url,
    get_connection_status,
)
from .models import Contact, Invoice, InventoryItem, ItemType, LineItem, ProcessedEmail, Vendor, VendorEmail
from .serializers import (
    ContactSerializer,
    InvoiceAutomationSettingsSerializer,
    InvoiceSerializer,
    InventoryItemSerializer,
    ItemTypeSerializer,
    LineItemSerializer,
    VendorSerializer,
)
from .services import (
    export_invoices_workbook,
    get_automation_settings,
    process_gmail_message,
    process_pending_gmail_invoices,
    update_automation_settings,
)
from django.conf import settings
from django.http import HttpResponseRedirect, HttpResponse
from django.db import models
import os
from datetime import datetime
import logging
import time
import re
import base64
import traceback

logger = logging.getLogger(__name__)

GMAIL_INVOICE_QUERY = 'has:attachment invoice'
MAX_EMAIL_PAGE_SIZE = 100
DEFAULT_EMAIL_PAGE_SIZE = 20
MAX_FILTER_BACKFILL_PAGES = 5

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


def get_module_functions(module_path):
    """
    Return vendor parser callables from a parser module file (not internal helpers).

    Only functions named parse_* that define a display ``.name`` attribute
    (e.g. ``parse_sierra_invoice.name = "Sierra Forest Products"``) are included.
    """
    import importlib.util
    import inspect

    module_name = os.path.splitext(os.path.basename(module_path))[0]

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    functions = []
    for name, obj in inspect.getmembers(module):
        if not inspect.isfunction(obj) or obj.__module__ != module_name:
            continue
        if not name.startswith("parse_"):
            continue
        display_name = getattr(obj, "name", None)
        if not display_name or not isinstance(display_name, str):
            continue
        functions.append({"method": name, "name": display_name})

    return sorted(functions, key=lambda entry: entry["name"].lower())


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



def _extract_sender_email(from_header):
    if not from_header:
        return None
    email_match = re.search(r'<(.+?)>|([^<\s]+@[^>\s]+)', from_header)
    if not email_match:
        return None
    return email_match.group(1) or email_match.group(2)


def _vendor_name_from_sender(from_header, sender_email):
    if not sender_email:
        return None
    if any(sender_email.endswith(f'@{domain}') for domain in SPECIAL_EMAIL_DOMAINS):
        name_match = re.search(r'^(.+?)\s*<', from_header or '')
        if name_match:
            return name_match.group(1).strip()
    domain_match = re.search(r'@(.+?)\.[^.]+$', sender_email)
    return domain_match.group(1).title() if domain_match else "Unknown"


def _sync_vendor_for_sender(from_header, sender_email):
    vendor_name = _vendor_name_from_sender(from_header, sender_email)
    if not vendor_name:
        return vendor_name, None
    try:
        vendor, _created = Vendor.objects.update_or_create(
            name=vendor_name,
            defaults={'invoice_type': 'pdf'},
        )
        VendorEmail.objects.update_or_create(
            email=sender_email,
            defaults={'vendor': vendor, 'is_primary': True},
        )
        return vendor_name, vendor.id
    except Exception as exc:
        logger.exception("Error creating/updating vendor for %s", sender_email)
        return vendor_name, None


def _gmail_date_token(iso_date):
    """Convert YYYY-MM-DD to Gmail after:/before: token (YYYY/MM/DD)."""
    if not iso_date:
        return None
    try:
        parsed = datetime.strptime(iso_date[:10], '%Y-%m-%d')
    except ValueError:
        return None
    return parsed.strftime('%Y/%m/%d')


def _build_gmail_list_query(search, vendor_id, date_from, date_to):
    parts = [GMAIL_INVOICE_QUERY]
    if search:
        parts.append(search)
    if vendor_id:
        vendor_emails = list(
            VendorEmail.objects.filter(vendor_id=vendor_id).values_list('email', flat=True)
        )
        if vendor_emails:
            from_parts = [f'from:{email}' for email in vendor_emails]
            parts.append(f"({' OR '.join(from_parts)})")
    after = _gmail_date_token(date_from)
    before = _gmail_date_token(date_to)
    if after:
        parts.append(f'after:{after}')
    if before:
        parts.append(f'before:{before}')
    return ' '.join(parts)


def _normalized_email_status(processed):
    if processed is None:
        return 'pending'
    return processed.status or 'pending'


def _email_matches_status(processed, status_filter):
    if not status_filter:
        return True
    return _normalized_email_status(processed) == status_filter


def _email_matches_search(item, search):
    if not search:
        return True
    needle = search.lower()
    haystacks = (
        item.get('snippet') or '',
        item.get('from') or '',
        item.get('vendor_name') or '',
    )
    return any(needle in value.lower() for value in haystacks)


def _email_matches_vendor_id(item_vendor_id, vendor_id_filter):
    if not vendor_id_filter:
        return True
    try:
        wanted = int(vendor_id_filter)
    except (TypeError, ValueError):
        return True
    return item_vendor_id == wanted


def _google_connection_error_response(exc):
    return Response(
        {'error': str(exc), 'connected': False},
        status=status.HTTP_409_CONFLICT,
    )


def _serialize_list_email(service, message_id, processed=None):
    email = service.users().messages().get(userId='me', id=message_id).execute()
    attachment_count = 0
    if 'payload' in email and 'parts' in email['payload']:
        attachment_count = sum(
            1 for part in email['payload']['parts'] if part.get('filename')
        )

    headers = email['payload'].get('headers', [])
    from_header = next(
        (header['value'] for header in headers if header['name'].lower() == 'from'),
        None,
    )
    date_header = next(
        (header['value'] for header in headers if header['name'].lower() == 'date'),
        None,
    )

    sender_email = _extract_sender_email(from_header)
    vendor_name = None
    inferred_vendor_id = None
    if sender_email:
        vendor_name, inferred_vendor_id = _sync_vendor_for_sender(from_header, sender_email)

    if processed is None:
        processed = (
            ProcessedEmail.objects.filter(email_id=message_id).select_related('vendor').first()
        )
    vendor_id = processed.vendor_id if processed and processed.vendor_id else inferred_vendor_id
    if processed and processed.vendor:
        vendor_name = processed.vendor.name

    return {
        'id': message_id,
        'snippet': email.get('snippet', ''),
        'attachment_count': attachment_count,
        'from': from_header,
        'date': date_header,
        'message_data': processed.data if processed else None,
        'status': _normalized_email_status(processed),
        'vendor_name': vendor_name,
        'vendor_id': vendor_id,
    }


@api_view(['GET'])
def list_invoice_emails(request):
    try:
        service = get_gmail_service()
    except RuntimeError as exc:
        return _google_connection_error_response(exc)
    page_token = request.GET.get('pageToken') or None
    try:
        page_size = int(request.GET.get('maxResults', DEFAULT_EMAIL_PAGE_SIZE))
    except (TypeError, ValueError):
        page_size = DEFAULT_EMAIL_PAGE_SIZE
    page_size = max(1, min(page_size, MAX_EMAIL_PAGE_SIZE))

    status_filter = (request.GET.get('status') or '').strip().lower() or None
    if status_filter and status_filter not in {'pending', 'processed', 'error'}:
        return Response({'error': f'Invalid status: {status_filter}'}, status=400)

    vendor_id = (request.GET.get('vendorId') or '').strip() or None
    search = (request.GET.get('search') or '').strip() or None
    date_from = (request.GET.get('dateFrom') or '').strip() or None
    date_to = (request.GET.get('dateTo') or '').strip() or None

    gmail_query = _build_gmail_list_query(search, vendor_id, date_from, date_to)
    needs_post_filter = bool(status_filter or search or vendor_id)

    emails = []
    next_page_token = page_token
    gmail_fetch_token = page_token
    backfill_pages = 0

    while len(emails) < page_size and backfill_pages < MAX_FILTER_BACKFILL_PAGES:
        results = service.users().messages().list(
            userId='me',
            q=gmail_query,
            maxResults=page_size,
            pageToken=gmail_fetch_token,
        ).execute()

        messages = results.get('messages', [])
        next_page_token = results.get('nextPageToken')
        gmail_fetch_token = next_page_token

        for msg in messages:
            processed = None
            if status_filter:
                processed = ProcessedEmail.objects.filter(email_id=msg['id']).first()
                if not _email_matches_status(processed, status_filter):
                    continue

            item = _serialize_list_email(service, msg['id'], processed=processed)
            if search and not _email_matches_search(item, search):
                continue
            if vendor_id and not _email_matches_vendor_id(item.get('vendor_id'), vendor_id):
                continue

            emails.append(item)
            if len(emails) >= page_size:
                break

        backfill_pages += 1
        if len(emails) >= page_size or not next_page_token:
            break
        if not needs_post_filter:
            break

    return Response({
        'emails': emails[:page_size],
        'nextPageToken': next_page_token,
        'pageSize': page_size,
        'hasMore': bool(next_page_token),
    })


@api_view(['POST'])
def process_invoice_email(request):
    email_id = request.data.get('email_id')
    try:
        service = get_gmail_service()
    except RuntimeError as exc:
        return _google_connection_error_response(exc)
    try:
        result = process_gmail_message(service, email_id)
        vendor = None
        if result.get('processed_email') and result['processed_email'].vendor_id:
            vendor = result['processed_email'].vendor

        return Response({
            'status': result.get('status', 'error'),
            'invoice': result.get('parsed', {}).get('invoices', [{}])[0] if result.get('parsed') else {},
            'vendor': VendorSerializer(vendor).data if vendor else None,
            'errors': [] if result.get('status') == 'processed' else [result.get('reason', 'Processing failed')],
        })
    except Exception as exc:
        logger.exception('Failed to process invoice email %s', email_id)
        return Response({'status': 'error', 'errors': [str(exc)]}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def test_parser(request):
    """
    Test a data rule against a PDF file.
    """
    print("test_parser")
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
        print("parser_func", parser_func)
        if not parser_func:
            return Response(
                {'error': f'Parser method {parser_method} not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Run the parser and coerce to the standard invoice schema
        from .parsers import normalize_parser_output

        result = parser_func(file_path)
        result = normalize_parser_output(
            result,
            vendor_name=getattr(parser_func, 'name', None),
        )

        if isinstance(result, dict) and 'error' in result:
            raise Exception(result['error'])

        return Response({
            'success': True,
            'method': parser_method,
            'result': result
        })

    except Exception as e:
        # Get the traceback information
        tb = traceback.extract_tb(e.__traceback__)
        if tb:
            # Get the last frame where the error occurred
            last_frame = tb[-1]
            error_info = {
                'error': str(e),
                'line_number': last_frame.lineno,
                'file': last_frame.filename,
                'function': last_frame.name
            }
        else:
            error_info = {
                'error': str(e),
                'line_number': 'unknown',
                'file': 'unknown',
                'function': 'unknown'
            }

        return Response(
            error_info,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def google_auth_url(request):
    authorization_url = get_authorization_url(request)
    return Response({'authorization_url': authorization_url})


@api_view(['GET'])
def google_oauth_callback(request):
    try:
        exchange_authorization_code(request)
        redirect_url = build_frontend_redirect({'googleAuth': 'success'})
    except Exception as exc:
        logger.exception('Google OAuth callback failed')
        redirect_url = build_frontend_redirect({
            'googleAuth': 'error',
            'message': str(exc),
        })

    return HttpResponseRedirect(redirect_url)


@api_view(['GET'])
def google_auth_status(request):
    return Response(get_connection_status())


@api_view(['POST'])
def google_disconnect(request):
    disconnect_credentials()
    return Response({'connected': False})


@api_view(['GET', 'PUT'])
def automation_settings_view(request):
    if request.method == 'GET':
        serializer = InvoiceAutomationSettingsSerializer(get_automation_settings())
        return Response(serializer.data)

    serializer = InvoiceAutomationSettingsSerializer(
        get_automation_settings(),
        data=request.data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    settings_obj = update_automation_settings(**serializer.validated_data)
    return Response(InvoiceAutomationSettingsSerializer(settings_obj).data)


@api_view(['POST'])
def process_invoices_now(request):
    limit = request.data.get('limit')
    try:
        limit = int(limit) if limit is not None else None
    except (TypeError, ValueError):
        limit = None
    try:
        return Response(process_pending_gmail_invoices(limit=limit))
    except RuntimeError as exc:
        return _google_connection_error_response(exc)


@api_view(['GET'])
def export_invoices_xlsx(request):
    workbook_bytes = export_invoices_workbook()
    response = HttpResponse(
        workbook_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="invoiceinator-export.xlsx"'
    return response


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.select_related('vendor', 'contact').prefetch_related('line_items').all()
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('q')
        if query:
            queryset = queryset.filter(
                models.Q(invoice_number__icontains=query)
                | models.Q(source_email_subject__icontains=query)
                | models.Q(source_email_from__icontains=query)
                | models.Q(vendor__name__icontains=query)
                | models.Q(contact__name__icontains=query)
            )
        return queryset.order_by('-received_at', '-processed_at', '-created_at')


class InventoryItemViewSet(viewsets.ModelViewSet):
    queryset = InventoryItem.objects.select_related('vendor', 'item_type').all()
    serializer_class = InventoryItemSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('q')
        if query:
            queryset = queryset.filter(
                models.Q(name__icontains=query)
                | models.Q(item_key__icontains=query)
                | models.Q(item_id__icontains=query)
                | models.Q(vendor__name__icontains=query)
                | models.Q(item_type__name__icontains=query)
            )
        return queryset.order_by('name', 'item_key')


class ItemTypeViewSet(viewsets.ModelViewSet):
    queryset = ItemType.objects.all()
    serializer_class = ItemTypeSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('q')
        if query:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('name')


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.select_related('vendor').all()
    serializer_class = ContactSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('q')
        if query:
            queryset = queryset.filter(
                models.Q(name__icontains=query)
                | models.Q(email__icontains=query)
                | models.Q(phone__icontains=query)
                | models.Q(vendor__name__icontains=query)
            )
        return queryset.order_by('name')


class LineItemViewSet(viewsets.ModelViewSet):
    queryset = LineItem.objects.select_related('invoice', 'inventory_item', 'item_type').all()
    serializer_class = LineItemSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('q')
        if query:
            queryset = queryset.filter(
                models.Q(name__icontains=query)
                | models.Q(description__icontains=query)
                | models.Q(item_id__icontains=query)
                | models.Q(invoice__invoice_number__icontains=query)
                | models.Q(item_type__name__icontains=query)
            )
        return queryset.order_by('-created_at')


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
        return super().update(request, *args, **kwargs)

    def get_queryset(self):
        """
        Optionally filter by name
        """
        queryset = Vendor.objects.all()
        query = self.request.query_params.get('q') or self.request.query_params.get('name')
        if query:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('name')

    @action(detail=False, methods=['get'])
    def get_invoice_parsers(self, request):
        """
        Get a list of available parser methods from the parsers package.
        """
        try:
            from .parsers import list_invoice_parsers

            available_parsers = list_invoice_parsers()
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
