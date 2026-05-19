from __future__ import annotations

from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from io import BytesIO
import logging
import os
import re
import threading
import time

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from openpyxl import Workbook

from . import parsers as parser_module
from .models import (
    Contact,
    Invoice,
    InvoiceAutomationSettings,
    InventoryItem,
    Job,
    LineItem,
    ItemType,
    ProcessedEmail,
    Vendor,
    VendorEmail,
)
from .parsers import list_invoice_parsers, normalize_parser_output
from .utils import get_gmail_service

logger = logging.getLogger(__name__)

_worker_thread = None
_worker_lock = threading.Lock()
_processing_lock = threading.Lock()

GMAIL_INVOICE_QUERY = 'has:attachment invoice'


def media_url_for_stored_filename(stored_filename):
    """Relative URL for saved PDFs (works with Vite /api and /media proxies)."""
    media_prefix = settings.MEDIA_URL.strip('/')
    return f'/{media_prefix}/{stored_filename}'


def attachment_info_for_message(message_id):
    """Find a previously saved PDF for this Gmail message id."""
    media_dir = settings.MEDIA_ROOT
    if not os.path.isdir(media_dir):
        return None

    prefix = f'{message_id}_'
    for name in sorted(os.listdir(media_dir)):
        if not name.startswith(prefix):
            continue
        if not name.lower().endswith('.pdf'):
            continue
        return {
            'filename': name,
            'original_filename': name[len(prefix):],
            'mimeType': 'application/pdf',
            'url': media_url_for_stored_filename(name),
        }
    return None


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
    special_domains = (
        'notification.intuit.com',
        'billtrust.com',
        'live.com',
        'outlook.com',
        'gmail.com',
        'yahoo.com',
        'hotmail.com',
        'msn.com',
    )
    if any(sender_email.endswith(f'@{domain}') for domain in special_domains):
        name_match = re.search(r'^(.+?)\s*<', from_header or '')
        if name_match:
            return name_match.group(1).strip()
    domain_match = re.search(r'@(.+?)\.[^.]+$', sender_email)
    return domain_match.group(1).title() if domain_match else 'Unknown'


def _sync_vendor_for_sender(from_header, sender_email):
    vendor_name = _vendor_name_from_sender(from_header, sender_email)
    if not vendor_name:
        return None
    vendor, _created = Vendor.objects.update_or_create(
        name=vendor_name,
        defaults={'invoice_type': 'pdf'},
    )
    VendorEmail.objects.update_or_create(
        email=sender_email,
        defaults={'vendor': vendor, 'is_primary': True},
    )
    return vendor


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    for fmt in ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return parsedate_to_datetime(str(value))
    except Exception:
        return None


def _decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _selected_parser_for_vendor(vendor):
    if not vendor:
        return None

    if vendor.parser:
        return getattr(parser_module, vendor.parser, None)

    parser_lookup = {
        entry['name'].lower(): entry['method']
        for entry in list_invoice_parsers()
    }
    vendor_name = vendor.name.lower()
    for display_name, method_name in parser_lookup.items():
        if vendor_name in display_name or display_name in vendor_name:
            return getattr(parser_module, method_name, None)
    return None


def _ensure_invoice_automation_settings():
    return InvoiceAutomationSettings.load()


def resolve_vendor_for_persist(vendor=None, parsed_output=None, email_payload=None):
    """Resolve vendor from explicit instance, parsed PDF data, or sender email."""
    if vendor is not None:
        return vendor
    vendor_name = (parsed_output or {}).get('vendor_name')
    if vendor_name:
        vendor, _ = Vendor.objects.get_or_create(
            name=str(vendor_name).strip(),
            defaults={'invoice_type': 'pdf'},
        )
        return vendor
    email_payload = email_payload or {}
    from_header = email_payload.get('from') or ''
    sender_email = _extract_sender_email(from_header)
    if sender_email:
        return _sync_vendor_for_sender(from_header, sender_email)
    return None


def resolve_contact(vendor, email_payload):
    """Get or create a contact from invoice email headers."""
    if not vendor:
        return None
    email_payload = email_payload or {}
    from_header = str(email_payload.get('from') or '').strip()
    sender_email = (_extract_sender_email(from_header) or '').strip()
    name = ''
    if from_header:
        name_match = re.search(r'^(.+?)\s*<', from_header)
        if name_match:
            name = name_match.group(1).strip().strip('"')
    if not name and sender_email:
        name = sender_email.split('@')[0].replace('.', ' ').title()
    if not sender_email and not name:
        return vendor.contacts.filter(is_primary=True).first()

    if sender_email:
        contact, _created = Contact.objects.get_or_create(
            vendor=vendor,
            email=sender_email,
            defaults={'name': name or sender_email, 'is_primary': False},
        )
    else:
        contact, _created = Contact.objects.get_or_create(
            vendor=vendor,
            name=name,
            email='',
            defaults={'is_primary': False},
        )
    if name and contact.name != name:
        contact.name = name
        contact.save(update_fields=['name', 'updated_at'])
    return contact


def resolve_job(vendor, job_id='', job_name=''):
    """Get or create a Job from parsed line-item job id and name."""
    job_id = str(job_id or '').strip()
    job_name = str(job_name or '').strip()
    if not job_id and not job_name:
        return None
    if job_id:
        job, _created = Job.objects.update_or_create(
            vendor=vendor,
            job_id=job_id,
            defaults={'name': job_name},
        )
        return job
    job, _ = Job.objects.get_or_create(
        vendor=vendor,
        job_id='',
        name=job_name,
    )
    return job


def _update_inventory_from_line_item(invoice, line_item, line_item_payload):
    item_key = str(line_item_payload.get('id') or line_item_payload.get('name') or '').strip()
    if not item_key:
        return None
    current_qty = _decimal(line_item_payload.get('qty')) or Decimal('0')
    inventory_item, _created = InventoryItem.objects.get_or_create(
        vendor=invoice.vendor,
        item_key=item_key,
        defaults={
            'item_type': line_item.item_type,
            'item_id': str(line_item_payload.get('id') or ''),
            'name': str(line_item_payload.get('name') or ''),
            'description': str(line_item_payload.get('description') or ''),
            'unit': str(line_item_payload.get('unit') or ''),
            'current_qty': current_qty,
            'last_unit_price': _decimal(line_item_payload.get('unit_price')),
            'last_total_price': _decimal(line_item_payload.get('total_price')),
            'last_invoiced_at': invoice.processed_at or timezone.now(),
            'metadata': {'last_invoice_id': invoice.id},
        },
    )
    if not _created:
        inventory_item.item_type = line_item.item_type or inventory_item.item_type
        inventory_item.item_id = str(line_item_payload.get('id') or inventory_item.item_id)
        inventory_item.name = str(line_item_payload.get('name') or inventory_item.name)
        inventory_item.description = str(line_item_payload.get('description') or inventory_item.description)
        inventory_item.unit = str(line_item_payload.get('unit') or inventory_item.unit)
        inventory_item.current_qty = (inventory_item.current_qty or Decimal('0')) + current_qty
        inventory_item.last_unit_price = _decimal(line_item_payload.get('unit_price'))
        inventory_item.last_total_price = _decimal(line_item_payload.get('total_price'))
        inventory_item.last_invoiced_at = invoice.processed_at or timezone.now()
        inventory_item.metadata = {**(inventory_item.metadata or {}), 'last_invoice_id': invoice.id}
        inventory_item.save(update_fields=[
            'item_type', 'item_id', 'name', 'description', 'unit', 'current_qty',
            'last_unit_price', 'last_total_price', 'last_invoiced_at', 'metadata', 'updated_at'
        ])
    line_item.inventory_item = inventory_item
    line_item.save(update_fields=['inventory_item', 'updated_at'])
    return inventory_item


def _create_line_items_for_invoice(invoice, vendor, invoice_payload):
    """Create LineItem, Job, ItemType, and InventoryItem rows from parser output."""
    for line_item_payload in invoice_payload.get('line_items', []) or []:
        item_type_name = str(
            line_item_payload.get('item_type') or line_item_payload.get('type') or ''
        ).strip()
        item_type = None
        if item_type_name:
            item_type, _ = ItemType.objects.get_or_create(name=item_type_name)
        line_item = LineItem.objects.create(
            invoice=invoice,
            item_type=item_type,
            job=resolve_job(
                vendor,
                line_item_payload.get('job_id'),
                line_item_payload.get('job'),
            ),
            item_id=str(line_item_payload.get('id') or ''),
            name=str(line_item_payload.get('name') or ''),
            description=str(line_item_payload.get('description') or ''),
            qty=_decimal(line_item_payload.get('qty')) or Decimal('0'),
            unit=str(line_item_payload.get('unit') or ''),
            unit_price=_decimal(line_item_payload.get('unit_price')) or Decimal('0'),
            total_price=_decimal(line_item_payload.get('total_price')) or Decimal('0'),
            width=_decimal(line_item_payload.get('width')),
            length=_decimal(line_item_payload.get('length')),
            height=_decimal(line_item_payload.get('height')),
            raw_data=line_item_payload,
        )
        _update_inventory_from_line_item(invoice, line_item, line_item_payload)


@transaction.atomic
def upsert_invoice_from_payload(message_id, email_payload, invoice_payload, vendor):
    """Create or update Invoice and related line items from one parsed invoice dict."""
    email_payload = email_payload or {}
    source_email_date = _parse_datetime(email_payload.get('date'))
    contact = resolve_contact(vendor, email_payload)
    if not contact and vendor:
        contact = vendor.contacts.filter(is_primary=True).first()

    defaults = {
        'vendor': vendor,
        'contact': contact,
        'source_email_subject': email_payload.get('subject') or '',
        'source_email_from': email_payload.get('from') or '',
        'source_email_date': source_email_date,
        'received_at': source_email_date or timezone.now(),
        'invoice_number': str(invoice_payload.get('invoice_number') or ''),
        'invoice_date': _parse_date(invoice_payload.get('date_ordered')),
        'ship_date': _parse_date(invoice_payload.get('ship_date')),
        'due_date': _parse_date(invoice_payload.get('invoice_due_date')),
        'customer_po': str(invoice_payload.get('cust_po') or ''),
        'invoice_total': _decimal(invoice_payload.get('invoice_total')),
        'status': 'processed',
        'processed_at': timezone.now(),
        'raw_data': invoice_payload,
    }
    invoice, created = Invoice.objects.update_or_create(
        source_email_id=message_id,
        defaults=defaults,
    )
    if not created:
        invoice.line_items.all().delete()
    _create_line_items_for_invoice(invoice, vendor, invoice_payload)
    return invoice


@transaction.atomic
def persist_parsed_invoices(vendor, email_payload, parsed_output, message_id_base):
    """
    Persist normalized parser output to Invoice, LineItem, Job, Contact, and InventoryItem.

    ``parsed_output`` is ``{vendor_name, invoices: [...]}`` from ``normalize_parser_output``.
    """
    parsed_output = parsed_output or {}
    email_payload = email_payload or {}
    vendor = resolve_vendor_for_persist(
        vendor=vendor,
        parsed_output=parsed_output,
        email_payload=email_payload,
    )
    invoices_data = parsed_output.get('invoices') or []
    if not invoices_data:
        return []

    saved = []
    for index, invoice_payload in enumerate(invoices_data, start=1):
        source_id = f'{message_id_base}:{index}'
        saved.append(
            upsert_invoice_from_payload(
                source_id,
                email_payload,
                invoice_payload,
                vendor,
            )
        )
    return saved


def save_parsed_invoice(message_id, email_payload, invoice_payload, vendor):
    """Backward-compatible alias for a single parsed invoice."""
    return upsert_invoice_from_payload(message_id, email_payload, invoice_payload, vendor)


def _line_item_to_parser_dict(line_item):
    job = line_item.job if line_item.job_id else None
    return {
        'id': line_item.item_id,
        'name': line_item.name,
        'description': line_item.description,
        'qty': str(line_item.qty),
        'unit': line_item.unit,
        'unit_price': float(line_item.unit_price),
        'total_price': float(line_item.total_price),
        'width': float(line_item.width) if line_item.width is not None else None,
        'length': float(line_item.length) if line_item.length is not None else None,
        'height': float(line_item.height) if line_item.height is not None else None,
        'job_id': job.job_id if job else '',
        'job': job.name if job else '',
    }


def invoice_to_parser_dict(invoice):
    """Map a saved Invoice to the parser-shaped dict used by the processing dialog."""
    if hasattr(invoice, 'line_items'):
        line_items = [
            _line_item_to_parser_dict(line_item)
            for line_item in invoice.line_items.select_related('job').all()
        ]
    else:
        line_items = []
        for line_item in (invoice.get('line_items') or []):
            line_items.append({
                'id': line_item.get('item_id') or line_item.get('id') or '',
                'name': line_item.get('name') or '',
                'description': line_item.get('description') or '',
                'qty': str(line_item.get('qty') or '1'),
                'unit': line_item.get('unit') or '',
                'unit_price': float(line_item.get('unit_price') or 0),
                'total_price': float(line_item.get('total_price') or 0),
                'width': line_item.get('width'),
                'length': line_item.get('length'),
                'height': line_item.get('height'),
                'job_id': line_item.get('job_number') or line_item.get('job_id') or '',
                'job': line_item.get('job_name') or line_item.get('job') or '',
            })

    def _date_str(value):
        if value is None or value == '':
            return None
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        return str(value)

    vendor_name = ''
    if hasattr(invoice, 'vendor') and invoice.vendor_id:
        vendor_name = invoice.vendor.name
    elif isinstance(invoice, dict):
        vendor_name = invoice.get('vendor_name') or ''

    if isinstance(invoice, dict):
        return {
            'invoice_number': invoice.get('invoice_number') or '',
            'vendor_name': vendor_name,
            'ship_date': _date_str(invoice.get('ship_date')),
            'date_ordered': _date_str(invoice.get('invoice_date') or invoice.get('date_ordered')),
            'invoice_due_date': _date_str(invoice.get('due_date') or invoice.get('invoice_due_date')),
            'cust_po': invoice.get('customer_po') or invoice.get('cust_po') or '',
            'invoice_total': (
                str(invoice['invoice_total'])
                if invoice.get('invoice_total') is not None
                else None
            ),
            'line_items': line_items,
        }

    return {
        'invoice_number': invoice.invoice_number,
        'vendor_name': vendor_name,
        'ship_date': _date_str(invoice.ship_date),
        'date_ordered': _date_str(invoice.invoice_date),
        'invoice_due_date': _date_str(invoice.due_date),
        'cust_po': invoice.customer_po,
        'invoice_total': (
            str(invoice.invoice_total) if invoice.invoice_total is not None else None
        ),
        'line_items': line_items,
    }


def parsed_envelope_for_process_result(result, email_id=None, vendor=None):
    """
    Build ``{vendor_name, invoices}`` for the processing dialog from parse results
    or saved Invoice rows.
    """
    parsed = result.get('parsed') if isinstance(result.get('parsed'), dict) else {}
    invoices = parsed.get('invoices') if parsed else None
    if invoices:
        vendor_name = parsed.get('vendor_name') or (vendor.name if vendor else '')
        return {'vendor_name': vendor_name, 'invoices': list(invoices)}

    # Legacy ProcessedEmail.data may store a single invoice dict.
    if parsed and (parsed.get('line_items') is not None or parsed.get('invoice_number')):
        vendor_name = parsed.get('vendor_name') or (vendor.name if vendor else '')
        return {'vendor_name': vendor_name, 'invoices': [parsed]}

    saved = result.get('invoices') or []
    if saved:
        if saved and hasattr(saved[0], 'pk'):
            invoice_ids = [invoice.pk for invoice in saved]
            saved = list(
                Invoice.objects.filter(pk__in=invoice_ids)
                .select_related('vendor')
                .prefetch_related('line_items__job')
                .order_by('source_email_id')
            )
        vendor_name = vendor.name if vendor else ''
        invoice_dicts = [invoice_to_parser_dict(invoice) for invoice in saved]
        if not vendor_name and invoice_dicts:
            vendor_name = invoice_dicts[0].get('vendor_name') or ''
        return {'vendor_name': vendor_name, 'invoices': invoice_dicts}

    if email_id:
        db_invoices = list(
            Invoice.objects.filter(
                Q(source_email_id=email_id)
                | Q(source_email_id__startswith=f'{email_id}:')
            )
            .select_related('vendor')
            .prefetch_related('line_items__job')
            .order_by('source_email_id')
        )
        if db_invoices:
            if not vendor and db_invoices[0].vendor_id:
                vendor = db_invoices[0].vendor
            vendor_name = vendor.name if vendor else (db_invoices[0].vendor.name if db_invoices[0].vendor_id else '')
            return {
                'vendor_name': vendor_name,
                'invoices': [invoice_to_parser_dict(invoice) for invoice in db_invoices],
            }

    return {'vendor_name': vendor.name if vendor else '', 'invoices': []}


def _list_message_ids(service, query):
    page_token = None
    while True:
        response = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=100,
            pageToken=page_token,
        ).execute()
        for message in response.get('messages', []):
            yield message['id']
        page_token = response.get('nextPageToken')
        if not page_token:
            break


def _select_attachment_part(payload_parts):
    for part in payload_parts or []:
        if part.get('filename') and part.get('mimeType', '').lower() in {'application/pdf', 'application/octet-stream'}:
            return part
    return None


def process_gmail_message(service, message_id):
    if ProcessedEmail.objects.filter(email_id=message_id, status='processed').exists():
        return {'status': 'skipped', 'reason': 'already processed'}

    email = service.users().messages().get(userId='me', id=message_id).execute()
    headers = email.get('payload', {}).get('headers', [])
    from_header = next((header['value'] for header in headers if header['name'].lower() == 'from'), '')
    subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), '')
    date_header = next((header['value'] for header in headers if header['name'].lower() == 'date'), '')
    sender_email = _extract_sender_email(from_header)
    vendor = _sync_vendor_for_sender(from_header, sender_email) if sender_email else None
    parser = _selected_parser_for_vendor(vendor)

    if not parser:
        processed_email, _ = ProcessedEmail.objects.update_or_create(
            email_id=message_id,
            defaults={
                'status': 'error',
                'processed': timezone.now(),
                'data': {'error': 'No parser configured for vendor', 'subject': subject},
                'vendor': vendor,
            },
        )
        return {'status': 'error', 'reason': 'no parser configured', 'processed_email': processed_email}

    payload = email.get('payload', {})
    attachment = _select_attachment_part(payload.get('parts', []))
    if not attachment:
        processed_email, _ = ProcessedEmail.objects.update_or_create(
            email_id=message_id,
            defaults={
                'status': 'error',
                'processed': timezone.now(),
                'data': {'error': 'No PDF attachment found', 'subject': subject},
                'vendor': vendor,
            },
        )
        return {'status': 'error', 'reason': 'no pdf attachment', 'processed_email': processed_email}

    attachment_payload = service.users().messages().attachments().get(
        userId='me',
        messageId=message_id,
        id=attachment['body']['attachmentId'],
    ).execute()

    from base64 import urlsafe_b64decode
    media_dir = settings.MEDIA_ROOT
    os.makedirs(media_dir, exist_ok=True)
    safe_filename = re.sub(r'[^a-zA-Z0-9.-]', '_', attachment['filename'])
    stored_filename = f'{message_id}_{safe_filename}'
    file_path = os.path.join(media_dir, stored_filename)
    with open(file_path, 'wb') as handle:
        handle.write(urlsafe_b64decode(attachment_payload['data'].encode('UTF-8')))

    attachment_info = {
        'filename': stored_filename,
        'original_filename': attachment['filename'],
        'mimeType': attachment.get('mimeType', 'application/pdf'),
        'url': media_url_for_stored_filename(stored_filename),
    }

    parsed = normalize_parser_output(
        parser(file_path),
        vendor_name=getattr(parser, 'name', None) or (vendor.name if vendor else None),
    )
    email_payload = {'from': from_header, 'subject': subject, 'date': date_header}
    created_invoices = persist_parsed_invoices(
        vendor,
        email_payload,
        parsed,
        message_id,
    )

    processed_email, _ = ProcessedEmail.objects.update_or_create(
        email_id=message_id,
        defaults={
            'status': 'processed',
            'processed': timezone.now(),
            'data': parsed,
            'vendor': vendor,
            'invoice': created_invoices[0] if created_invoices else None,
        },
    )
    return {
        'status': 'processed',
        'processed_email': processed_email,
        'invoices': created_invoices,
        'parsed': parsed,
        'attachment': attachment_info,
    }


def process_pending_gmail_invoices(limit=None):
    settings_obj = _ensure_invoice_automation_settings()
    if not settings_obj.auto_process_enabled:
        return {'status': 'disabled', 'processed': 0}

    service = get_gmail_service()
    cutoff = timezone.now() - timedelta(days=settings_obj.max_email_age_days)
    query = f"{GMAIL_INVOICE_QUERY} after:{cutoff.strftime('%Y/%m/%d')}"

    processed = 0
    results = []
    for message_id in _list_message_ids(service, query):
        if limit is not None and processed >= limit:
            break
        if ProcessedEmail.objects.filter(email_id=message_id, status='processed').exists():
            continue
        try:
            result = process_gmail_message(service, message_id)
            if result.get('status') == 'processed':
                processed += 1
            results.append(result)
        except Exception as exc:
            logger.exception('Error auto-processing message %s', message_id)
            ProcessedEmail.objects.update_or_create(
                email_id=message_id,
                defaults={
                    'status': 'error',
                    'processed': timezone.now(),
                    'data': {'error': str(exc)},
                },
            )

    settings_obj.last_processed_at = timezone.now()
    settings_obj.save(update_fields=['last_processed_at', 'updated_at'])
    return {'status': 'ok', 'processed': processed, 'results': results}


def get_automation_settings():
    return _ensure_invoice_automation_settings()


def update_automation_settings(**kwargs):
    settings_obj = _ensure_invoice_automation_settings()
    for field in ('auto_process_enabled', 'max_email_age_days', 'poll_interval_seconds'):
        if field in kwargs and kwargs[field] is not None:
            setattr(settings_obj, field, kwargs[field])
    settings_obj.save()
    return settings_obj


def export_invoices_workbook():
    workbook = Workbook()
    invoice_sheet = workbook.active
    invoice_sheet.title = 'Invoices'
    line_sheet = workbook.create_sheet('Line Items')
    inventory_sheet = workbook.create_sheet('Inventory')

    invoice_headers = [
        'Invoice ID', 'Source Email ID', 'Vendor', 'Contact', 'Invoice Number', 'Invoice Date',
        'Received At', 'Ship Date', 'Due Date', 'Customer PO', 'Invoice Total', 'Status',
        'Processed At', 'Source Email From', 'Source Email Subject',
    ]
    line_headers = [
        'Invoice ID', 'Invoice Number', 'Item Type', 'Item ID', 'Name', 'Description',
        'Job ID', 'Job Name',
        'Qty', 'Unit', 'Unit Price', 'Total Price', 'Width', 'Length', 'Height',
    ]
    inventory_headers = [
        'Item ID', 'Vendor', 'Item Type', 'Item Key', 'Name', 'Description', 'Unit', 'Current Qty',
        'Last Unit Price', 'Last Total Price', 'Last Invoiced At',
    ]

    invoice_sheet.append(invoice_headers)
    line_sheet.append(line_headers)
    inventory_sheet.append(inventory_headers)

    for invoice in Invoice.objects.select_related('vendor').prefetch_related('line_items').order_by('-received_at', '-processed_at', '-created_at'):
        invoice_sheet.append([
            invoice.id,
            invoice.source_email_id,
            invoice.vendor.name if invoice.vendor else '',
            invoice.contact.name if invoice.contact else '',
            invoice.invoice_number,
            invoice.invoice_date.isoformat() if invoice.invoice_date else '',
            invoice.received_at.isoformat() if invoice.received_at else '',
            invoice.ship_date.isoformat() if invoice.ship_date else '',
            invoice.due_date.isoformat() if invoice.due_date else '',
            invoice.customer_po,
            float(invoice.invoice_total) if invoice.invoice_total is not None else '',
            invoice.status,
            invoice.processed_at.isoformat() if invoice.processed_at else '',
            invoice.source_email_from,
            invoice.source_email_subject,
        ])

        for line_item in invoice.line_items.all():
            line_sheet.append([
                invoice.id,
                invoice.invoice_number,
                line_item.item_type.name if line_item.item_type else '',
                line_item.item_id,
                line_item.name,
                line_item.description,
                line_item.job.job_id if line_item.job_id else '',
                line_item.job.name if line_item.job_id else '',
                float(line_item.qty),
                line_item.unit,
                float(line_item.unit_price),
                float(line_item.total_price),
                float(line_item.width) if line_item.width is not None else '',
                float(line_item.length) if line_item.length is not None else '',
                float(line_item.height) if line_item.height is not None else '',
            ])

    for item in InventoryItem.objects.select_related('vendor').order_by('name', 'item_key'):
        inventory_sheet.append([
            item.id,
            item.vendor.name if item.vendor else '',
            item.item_type.name if item.item_type else '',
            item.item_key,
            item.name,
            item.description,
            item.unit,
            float(item.current_qty),
            float(item.last_unit_price) if item.last_unit_price is not None else '',
            float(item.last_total_price) if item.last_total_price is not None else '',
            item.last_invoiced_at.isoformat() if item.last_invoiced_at else '',
        ])

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def gmail_message_id_from_source_email_id(source_email_id):
    """Gmail message id from invoice ``source_email_id`` (may include ``:index`` suffix)."""
    if not source_email_id:
        return ''
    return source_email_id.split(':', 1)[0]


def reset_processed_email_after_invoice_deleted(invoice):
    """
    When the last invoice from a Gmail message is removed, reset ProcessedEmail so the
    email can be imported again.
    """
    message_id = gmail_message_id_from_source_email_id(invoice.source_email_id)
    if not message_id:
        return

    still_linked = Invoice.objects.filter(
        Q(source_email_id=message_id) | Q(source_email_id__startswith=f'{message_id}:')
    ).exclude(pk=invoice.pk).exists()
    if still_linked:
        return

    ProcessedEmail.objects.filter(email_id=message_id).update(
        status='pending',
        processed=None,
        invoice=None,
    )


def start_autoprocess_worker():
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return _worker_thread

        def _run():
            while True:
                poll_interval = 60
                try:
                    settings_obj = _ensure_invoice_automation_settings()
                    poll_interval = max(15, settings_obj.poll_interval_seconds)
                    if settings_obj.auto_process_enabled:
                        if _processing_lock.acquire(blocking=False):
                            try:
                                process_pending_gmail_invoices()
                            finally:
                                _processing_lock.release()
                except Exception:
                    logger.exception('Auto-processing worker failed')
                time.sleep(poll_interval)

        _worker_thread = threading.Thread(target=_run, name='invoiceinator-autoprocess', daemon=True)
        _worker_thread.start()
        return _worker_thread
