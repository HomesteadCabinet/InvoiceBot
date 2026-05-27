import json
import os
import base64
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.test import override_settings
from django.utils import timezone

from .models import (
    Contact,
    EmailMessageCache,
    InventoryItem,
    Invoice,
    InvoiceAutomationSettings,
    ItemType,
    Job,
    LineItem,
    ProcessedEmail,
    Vendor,
    VendorEmail,
)
from .item_types import resolve_item_type
from .serializers import ItemTypeSerializer, VendorSerializer
from .services import (
    process_pending_gmail_invoices,
    gmail_message_id_from_source_email_id,
    process_gmail_message,
    parsed_envelope_for_process_result,
    persist_parsed_invoices,
    reset_invoice_data,
    reset_processed_email_after_invoice_deleted,
    vendor_is_ignored,
    _selected_parser_for_vendor,
)
from .parsers import (
    make_line_item,
    normalize_parser_output,
    normalize_quantity,
    parse_generic_invoice,
    parse_rugby_invoice,
)
from .parsers import parse_ipaco_invoice
from .parsers import parse_mcmaster_carr_invoice
from .parsers import parse_sherwin_invoice
from .parsers import parse_weinig_invoice
from .parsers import parse_yates_mouldings_invoice


class ProcessedEmailResetOnInvoiceDeleteTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name='Test Vendor', invoice_type='pdf')
        self.message_id = 'gmail-msg-abc123'

    def _create_invoice(self, source_email_id):
        return Invoice.objects.create(
            vendor=self.vendor,
            source_email_id=source_email_id,
            status='processed',
            processed_at=timezone.now(),
        )

    def _create_processed_email(self):
        return ProcessedEmail.objects.create(
            email_id=self.message_id,
            status='processed',
            processed=timezone.now(),
            vendor=self.vendor,
        )

    def test_gmail_message_id_strips_index_suffix(self):
        self.assertEqual(
            gmail_message_id_from_source_email_id('gmail-msg-abc123:2'),
            'gmail-msg-abc123',
        )

    def test_resets_processed_email_when_last_invoice_deleted(self):
        processed = self._create_processed_email()
        invoice = self._create_invoice(f'{self.message_id}:1')
        processed.invoice = invoice
        processed.save(update_fields=['invoice'])

        reset_processed_email_after_invoice_deleted(invoice)
        invoice.delete()

        processed.refresh_from_db()
        self.assertEqual(processed.status, 'pending')
        self.assertIsNone(processed.processed)
        self.assertIsNone(processed.invoice_id)


class SelectedParserTests(TestCase):
    def test_sherwin_vendor_name_defaults_to_sherwin_parser(self):
        vendor = Vendor.objects.create(name='Sherwin Williams', invoice_type='pdf')
        parser = _selected_parser_for_vendor(vendor)
        self.assertIsNotNone(parser)
        self.assertEqual(getattr(parser, '__name__', ''), 'parse_sherwin_invoice')


class ParserSchemaTests(TestCase):
    def test_phone_sized_quantity_values_are_zeroed(self):
        self.assertEqual(normalize_quantity('15320149005'), '0')
        self.assertEqual(normalize_quantity('412680060'), '0')
        self.assertEqual(
            make_line_item(name='Richelieu suspect', qty='15,320,149,005')['qty'],
            '0',
        )

    def test_valid_quantity_values_are_normalized(self):
        self.assertEqual(normalize_quantity('2.0000'), '2')
        self.assertEqual(normalize_quantity('1,250.5000'), '1250.5')


class NestedItemTypeTests(TestCase):
    def test_item_type_full_path_for_nested_types(self):
        hardware = ItemType.objects.create(name='Hardware')
        screws = ItemType.objects.create(name='Screws', parent=hardware)
        self.assertEqual(screws.get_full_path(), 'Hardware › Screws')
        self.assertEqual(hardware.get_full_path(), 'Hardware')

    def test_resolve_item_type_supports_nested_path(self):
        item_type = resolve_item_type('Hardware > Screws')
        self.assertEqual(item_type.name, 'Screws')
        self.assertEqual(item_type.parent.name, 'Hardware')

    def test_item_type_parent_cannot_create_cycle(self):
        root = ItemType.objects.create(name='Root')
        child = ItemType.objects.create(name='Child', parent=root)
        serializer = ItemTypeSerializer(
            instance=root,
            data={'name': 'Root', 'parent': child.id},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('parent', serializer.errors)

    def test_sibling_names_unique_under_same_parent(self):
        parent = ItemType.objects.create(name='Parent')
        ItemType.objects.create(name='Child', parent=parent)
        serializer = ItemTypeSerializer(data={'name': 'Child', 'parent': parent.id})
        self.assertFalse(serializer.is_valid())
        self.assertTrue('name' in serializer.errors or 'non_field_errors' in serializer.errors)


class VendorProfileTests(TestCase):
    def test_vendor_serializer_exposes_profile_fields(self):
        vendor = Vendor.objects.create(
            name='Acme Supply',
            invoice_type='pdf',
            email='orders@acme.example',
            phone='555-0100',
            city='Portland',
            state='OR',
            ignore=True,
        )
        data = VendorSerializer(vendor).data
        self.assertTrue(data['ignore'])
        self.assertEqual(data['email'], 'orders@acme.example')
        self.assertEqual(data['city'], 'Portland')

    def test_vendor_is_ignored_helper(self):
        vendor = Vendor.objects.create(name='Ignored Vendor', invoice_type='pdf', ignore=True)
        self.assertTrue(vendor_is_ignored(vendor))
        self.assertFalse(vendor_is_ignored(None))


class PersistParsedInvoicesTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(
            name='Hafele America Co.',
            invoice_type='pdf',
        )

    def test_vendor_can_have_multiple_blank_email_contacts(self):
        first = Contact.objects.create(
            vendor=self.vendor,
            name='First Contact',
            email='',
        )
        second = Contact.objects.create(
            vendor=self.vendor,
            name='Second Contact',
            email='',
        )

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(Contact.objects.filter(vendor=self.vendor, email='').count(), 2)

    def test_persist_updates_contact_name_without_updated_at_field(self):
        Contact.objects.create(
            vendor=self.vendor,
            name='Old Name',
            email='orders@homestead.example',
        )

        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': '1001',
                'date_ordered': 'Apr 9, 2026',
                'invoice_total': '10.00',
                'line_items': [],
            }],
        }
        email_payload = {
            'from': 'Homestead Cabinet <orders@homestead.example>',
            'subject': 'Invoice attached',
            'date': 'Thu, 9 Apr 2026 12:00:00 +0000',
        }

        saved = persist_parsed_invoices(
            self.vendor,
            email_payload,
            parsed,
            'test-msg-contact',
        )

        self.assertEqual(len(saved), 1)
        contact = Contact.objects.get(vendor=self.vendor, email='orders@homestead.example')
        self.assertEqual(contact.name, 'Homestead Cabinet')

    def test_persist_creates_invoice_line_items_job_contact_inventory(self):
        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': '513395821',
                'date_ordered': 'Apr 9, 2026',
                'cust_po': '25668',
                'invoice_total': '515.25',
                'line_items': [{
                    'id': '546.63.116',
                    'name': 'Dispensa Tray Set',
                    'description': 'Dispensa Tray Set',
                    'job_id': '25668',
                    'job': 'LOHSS B1',
                    'qty': '2',
                    'unit': 'Set',
                    'unit_price': 257.625,
                    'total_price': 515.25,
                }],
            }],
        }
        email_payload = {
            'from': 'Homestead Cabinet <orders@homestead.example>',
            'subject': 'Invoice attached',
            'date': 'Thu, 9 Apr 2026 12:00:00 +0000',
        }
        saved = persist_parsed_invoices(
            self.vendor,
            email_payload,
            parsed,
            'test-msg-001',
        )
        self.assertEqual(len(saved), 1)
        invoice = saved[0]
        self.assertEqual(invoice.invoice_number, '513395821')
        self.assertEqual(invoice.customer_po, '25668')
        self.assertEqual(invoice.line_items.count(), 1)

        contact = Contact.objects.get(vendor=self.vendor, email='orders@homestead.example')
        self.assertEqual(invoice.contact_id, contact.id)

        job = Job.objects.get(vendor=self.vendor, job_id='25668')
        self.assertEqual(job.name, 'LOHSS B1')
        line = LineItem.objects.get(invoice=invoice)
        self.assertEqual(line.job_id, job.id)
        self.assertFalse(line.received)
        self.assertEqual(line.notes, '')

        inventory = InventoryItem.objects.get(vendor=self.vendor, item_key='dispensa tray set')
        self.assertEqual(inventory.name, 'Dispensa Tray Set')
        self.assertEqual(inventory.current_qty, 2)
        self.assertEqual(line.inventory_item_id, inventory.id)
        self.assertIsNone(invoice.received_at)

    def test_persist_accepts_po_and_job_aliases(self):
        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': 'ALIASES-001',
                'customer_po': 'PO-789',
                'line_items': [{
                    'id': 'ALIAS-ITEM',
                    'name': 'Alias Item',
                    'job_number': 'JOB-123',
                    'job_name': 'Alias Job',
                    'qty': '1',
                    'unit_price': 10,
                    'total_price': 10,
                }],
            }],
        }

        saved = persist_parsed_invoices(self.vendor, {}, parsed, 'test-msg-aliases')
        invoice = saved[0]

        self.assertEqual(invoice.customer_po, 'PO-789')
        job = Job.objects.get(vendor=self.vendor, job_id='JOB-123')
        self.assertEqual(job.name, 'Alias Job')
        line = LineItem.objects.get(invoice=invoice)
        self.assertEqual(line.job_id, job.id)

    def test_persist_combines_inventory_items_by_name_and_sums_qty(self):
        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': '513395822',
                'line_items': [{
                    'id': 'A-1',
                    'name': 'Tray',
                    'qty': '2',
                    'unit_price': 10,
                    'total_price': 20,
                }, {
                    'id': 'A-2',
                    'name': 'Tray',
                    'qty': '3',
                    'unit_price': 10,
                    'total_price': 30,
                }],
            }],
        }
        saved = persist_parsed_invoices(self.vendor, {}, parsed, 'test-msg-002a')
        invoice = saved[0]
        inventory_items = InventoryItem.objects.filter(vendor=self.vendor, item_key='tray')
        self.assertEqual(inventory_items.count(), 1)
        inventory = inventory_items.get()
        self.assertEqual(inventory.current_qty, 5)
        self.assertEqual(invoice.line_items.count(), 2)
        self.assertEqual(
            set(invoice.line_items.values_list('inventory_item_id', flat=True)),
            {inventory.id},
        )

    def test_persist_zeros_phone_sized_line_item_qty_and_skips_inventory(self):
        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': 'PHONE-QTY-001',
                'line_items': [{
                    'id': 'PHONE-1',
                    'name': '26430 parker dooher',
                    'qty': '15320149005',
                    'unit_price': 1,
                    'total_price': 1,
                }, {
                    'id': 'PHONE-2',
                    'name': 'net 15 mf',
                    'qty': '412680060',
                    'unit_price': 1,
                    'total_price': 1,
                }],
            }],
        }

        saved = persist_parsed_invoices(self.vendor, {}, parsed, 'test-msg-phone-qty')
        invoice = saved[0]

        self.assertEqual(list(invoice.line_items.values_list('qty', flat=True)), [0, 0])
        self.assertEqual(InventoryItem.objects.filter(vendor=self.vendor).count(), 0)

    def test_line_items_can_be_filtered_by_inventory_item(self):
        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': '513395823',
                'line_items': [{
                    'id': 'B-1',
                    'name': 'Bracket',
                    'qty': '4',
                    'unit_price': 5,
                    'total_price': 20,
                }],
            }],
        }
        persist_parsed_invoices(self.vendor, {}, parsed, 'test-msg-002b')
        inventory = InventoryItem.objects.get(vendor=self.vendor, item_key='bracket')

        response = self.client.get(f'/api/line-items/?inventory_item={inventory.id}')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(len(payload['results']), 1)
        self.assertEqual(payload['results'][0]['name'], 'Bracket')

    def test_persist_updates_existing_invoice_by_source_email_id(self):
        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': 'OLD',
                'line_items': [],
            }],
        }
        persist_parsed_invoices(self.vendor, {}, parsed, 'test-msg-002')
        parsed['invoices'][0]['invoice_number'] = 'NEW'
        parsed['invoices'][0]['line_items'] = [{
            'id': '1',
            'name': 'Widget',
            'qty': '1',
            'unit_price': 10,
            'total_price': 10,
        }]
        saved = persist_parsed_invoices(self.vendor, {}, parsed, 'test-msg-002')
        self.assertEqual(Invoice.objects.filter(source_email_id='test-msg-002:1').count(), 1)
        self.assertEqual(saved[0].invoice_number, 'NEW')
        self.assertEqual(saved[0].line_items.count(), 1)

    def test_reprocessing_preserves_manual_invoice_and_line_item_state(self):
        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': '513395821',
                'line_items': [{
                    'id': '546.63.116',
                    'name': 'Tray',
                    'qty': '1',
                    'unit_price': 10,
                    'total_price': 10,
                }],
            }],
        }
        saved = persist_parsed_invoices(self.vendor, {}, parsed, 'test-msg-003')
        invoice = saved[0]
        invoice.received_at = timezone.now()
        invoice.save(update_fields=['received_at'])

        line = invoice.line_items.get()
        line.received = True
        line.notes = 'Checked in at dock'
        line.save(update_fields=['received', 'notes'])

        parsed['invoices'][0]['invoice_number'] = 'UPDATED'
        parsed['invoices'][0]['line_items'][0]['name'] = 'Tray'
        saved_again = persist_parsed_invoices(self.vendor, {}, parsed, 'test-msg-003')

        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.received_at)
        self.assertEqual(invoice.invoice_number, 'UPDATED')
        self.assertEqual(saved_again[0].line_items.count(), 1)

        line = saved_again[0].line_items.get()
        self.assertTrue(line.received)
        self.assertEqual(line.notes, 'Checked in at dock')
        inventory = InventoryItem.objects.get(vendor=self.vendor, item_key='tray')
        self.assertEqual(inventory.current_qty, 1)

    def test_parsed_envelope_from_saved_invoices_for_dialog(self):
        parsed = {
            'vendor_name': 'Hafele America Co.',
            'invoices': [{
                'invoice_number': '513395821',
                'line_items': [{
                    'id': '546.63.116',
                    'name': 'Tray',
                    'job_id': '25668',
                    'job': 'LOHSS B1',
                    'qty': '1',
                    'unit_price': 10,
                    'total_price': 10,
                }],
            }],
        }
        saved = persist_parsed_invoices(self.vendor, {}, parsed, 'dialog-msg-001')
        envelope = parsed_envelope_for_process_result(
            {'parsed': {}, 'invoices': saved},
            email_id='dialog-msg-001',
            vendor=self.vendor,
        )
        self.assertEqual(len(envelope['invoices']), 1)
        self.assertEqual(envelope['invoices'][0]['invoice_number'], '513395821')
        self.assertEqual(len(envelope['invoices'][0]['line_items']), 1)
        self.assertEqual(envelope['invoices'][0]['line_items'][0]['job_id'], '25668')


class CrudPaginationTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name='Test Vendor', invoice_type='pdf')
        for index in range(25):
            InventoryItem.objects.create(
                vendor=self.vendor,
                item_key=f'item-{index}',
                name=f'Item {index:02d}',
                current_qty=index,
            )

    def test_inventory_items_paginate_by_default(self):
        response = self.client.get('/api/inventory-items/')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['count'], 25)
        self.assertEqual(len(payload['results']), 20)

    def test_inventory_items_respect_requested_page_size(self):
        response = self.client.get('/api/inventory-items/?page_size=5')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['count'], 25)
        self.assertEqual(len(payload['results']), 5)


class InvoiceEmailListCacheTests(TestCase):
    class FakeExecute:
        def __init__(self, payload):
            self.payload = payload

        def execute(self):
            return self.payload

    class FakeMessages:
        def __init__(self, owner):
            self.owner = owner

        def list(self, **_kwargs):
            return InvoiceEmailListCacheTests.FakeExecute({
                'messages': [{'id': 'msg-1'}, {'id': 'msg-2'}],
            })

        def get(self, **kwargs):
            self.owner.get_calls.append(kwargs)
            message_id = kwargs['id']
            return InvoiceEmailListCacheTests.FakeExecute({
                'id': message_id,
                'threadId': f'thread-{message_id}',
                'snippet': f'Snippet {message_id}',
                'payload': {
                    'headers': [
                        {'name': 'From', 'value': f'Sender {message_id} <sender-{message_id}@example.com>'},
                        {'name': 'Subject', 'value': f'Invoice {message_id}'},
                        {'name': 'Date', 'value': 'Thu, 9 Apr 2026 12:00:00 +0000'},
                    ],
                    'parts': [
                        {'filename': f'{message_id}.pdf', 'mimeType': 'application/pdf'},
                    ],
                },
            })

    class FakeUsers:
        def __init__(self, owner):
            self.owner = owner

        def messages(self):
            return InvoiceEmailListCacheTests.FakeMessages(self.owner)

    class FakeGmailService:
        def __init__(self):
            self.get_calls = []

        def users(self):
            return InvoiceEmailListCacheTests.FakeUsers(self)

    def test_list_invoice_emails_caches_metadata(self):
        service = self.FakeGmailService()

        with patch('invoices.views.get_gmail_service', return_value=service):
            first_response = self.client.get('/api/emails/?maxResults=2')
            second_response = self.client.get('/api/emails/?maxResults=2')

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(len(first_response.json()['emails']), 2)
        self.assertEqual(len(second_response.json()['emails']), 2)
        self.assertEqual(len(service.get_calls), 2)
        self.assertEqual(EmailMessageCache.objects.count(), 2)
        self.assertTrue(all(call.get('format') == 'metadata' for call in service.get_calls))

    def test_list_invoice_emails_returns_cached_attachment(self):
        EmailMessageCache.objects.create(
            email_id='msg-1',
            snippet='Cached snippet',
            from_header='Cached Sender <cached@example.com>',
            date_header='Thu, 9 Apr 2026 12:00:00 +0000',
            attachment_count=1,
            attachment_filename='msg-1_Vendor_PO.pdf',
            attachment_original_filename='invoice.pdf',
            attachment_mime_type='application/pdf',
        )
        service = self.FakeGmailService()

        with patch('invoices.views.get_gmail_service', return_value=service):
            response = self.client.get('/api/emails/?maxResults=2')

        self.assertEqual(response.status_code, 200)
        emails = response.json()['emails']
        cached_email = next(email for email in emails if email['id'] == 'msg-1')
        self.assertEqual(cached_email['attachment']['filename'], 'msg-1_Vendor_PO.pdf')
        self.assertEqual(cached_email['attachments'][0]['original_filename'], 'invoice.pdf')

    def test_list_invoice_emails_does_not_create_vendors(self):
        service = self.FakeGmailService()

        with patch('invoices.views.get_gmail_service', return_value=service):
            response = self.client.get('/api/emails/?maxResults=2')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vendor.objects.count(), 0)
        self.assertEqual(response.json()['emails'][0]['vendor_name'], 'Example')

    def test_list_invoice_emails_excludes_ignored_vendor(self):
        ignored_vendor = Vendor.objects.create(
            name='Ignored Vendor',
            invoice_type='pdf',
            ignore=True,
        )
        VendorEmail.objects.create(
            vendor=ignored_vendor,
            email='sender-msg-1@example.com',
            is_primary=True,
        )
        EmailMessageCache.objects.create(
            email_id='msg-1',
            snippet='Ignored vendor email',
            from_header='Ignored Vendor <sender-msg-1@example.com>',
            vendor=ignored_vendor,
        )
        service = self.FakeGmailService()

        with patch('invoices.views.get_gmail_service', return_value=service):
            response = self.client.get('/api/emails/?maxResults=5')

        self.assertEqual(response.status_code, 200)
        email_ids = [email['id'] for email in response.json()['emails']]
        self.assertNotIn('msg-1', email_ids)
        self.assertIn('msg-2', email_ids)


class FlagIncorrectParsingTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name='Flag Vendor', invoice_type='pdf')
        EmailMessageCache.objects.create(
            email_id='msg-flag-1',
            snippet='Bad parse',
            from_header='Flag Vendor <flag@example.com>',
            vendor=self.vendor,
        )

    def test_flag_creates_processed_email_with_incorrect_parsing_status(self):
        response = self.client.post(
            '/api/emails/flag-incorrect-parsing/',
            data={'email_id': 'msg-flag-1'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'incorrect_parsing')

        processed = ProcessedEmail.objects.get(email_id='msg-flag-1')
        self.assertEqual(processed.status, 'incorrect_parsing')
        self.assertEqual(processed.vendor_id, self.vendor.id)
        self.assertTrue(processed.data.get('flagged_incorrect_parsing'))

    def test_flag_updates_existing_processed_email(self):
        ProcessedEmail.objects.create(
            email_id='msg-flag-1',
            status='processed',
            processed=timezone.now(),
            data={'invoices': []},
            vendor=self.vendor,
        )

        response = self.client.post(
            '/api/emails/flag-incorrect-parsing/',
            data={'email_id': 'msg-flag-1'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        processed = ProcessedEmail.objects.get(email_id='msg-flag-1')
        self.assertEqual(processed.status, 'incorrect_parsing')

    def test_list_emails_filter_by_incorrect_parsing_status(self):
        ProcessedEmail.objects.create(
            email_id='msg-1',
            status='incorrect_parsing',
            processed=timezone.now(),
            vendor=self.vendor,
        )
        service = InvoiceEmailListCacheTests.FakeGmailService()

        with patch('invoices.views.get_gmail_service', return_value=service):
            response = self.client.get('/api/emails/?maxResults=5&status=incorrect_parsing')

        self.assertEqual(response.status_code, 200)
        emails = response.json()['emails']
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0]['id'], 'msg-1')
        self.assertEqual(emails[0]['status'], 'incorrect_parsing')

    def test_flag_requires_email_id(self):
        response = self.client.post(
            '/api/emails/flag-incorrect-parsing/',
            data={},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class InvoiceViewSetTests(TestCase):
    def setUp(self):
        self.vendor_one = Vendor.objects.create(name='Vendor One', invoice_type='pdf')
        self.vendor_two = Vendor.objects.create(name='Vendor Two', invoice_type='pdf')
        self.invoice_one = Invoice.objects.create(
            vendor=self.vendor_one,
            source_email_id='vendor-one-invoice-1',
            invoice_number='V1-001',
        )
        self.invoice_two = Invoice.objects.create(
            vendor=self.vendor_two,
            source_email_id='vendor-two-invoice-1',
            invoice_number='V2-001',
        )
        LineItem.objects.create(invoice=self.invoice_one, name='First Item')
        LineItem.objects.create(invoice=self.invoice_one, name='Second Item')
        LineItem.objects.create(invoice=self.invoice_two, name='Only Item')

    def test_invoices_can_be_filtered_by_vendor_id(self):
        response = self.client.get(f'/api/invoices/?vendorId={self.vendor_one.id}')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(len(payload['results']), 1)
        self.assertEqual(payload['results'][0]['invoice_number'], 'V1-001')

    def test_invoices_exclude_ignored_vendors(self):
        self.vendor_two.ignore = True
        self.vendor_two.save(update_fields=['ignore'])

        response = self.client.get('/api/invoices/')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['invoice_number'], 'V1-001')

    def test_invoices_can_be_ordered_by_vendor_name(self):
        response = self.client.get('/api/invoices/?ordering=-vendor__name')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(
            [invoice['invoice_number'] for invoice in payload['results']],
            ['V2-001', 'V1-001'],
        )

    def test_invoices_can_be_ordered_by_line_item_count(self):
        response = self.client.get('/api/invoices/?ordering=-line_item_count_sort')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(
            [invoice['invoice_number'] for invoice in payload['results']],
            ['V1-001', 'V2-001'],
        )


class ProcessGmailMessageAttachmentTests(TestCase):
    def _fake_service(self, attachment_data):
        class FakeAttachmentExecute:
            def execute(self_inner):
                return {'data': attachment_data}

        class FakeAttachments:
            def get(self_inner, **kwargs):
                return FakeAttachmentExecute()

        class FakeMessages:
            def get(self_inner, **kwargs):
                class FakeExecute:
                    def execute(self):
                        return {
                            'payload': {
                                'headers': [
                                    {'name': 'From', 'value': 'No Parser Vendor <orders@noparser.example>'},
                                    {'name': 'Subject', 'value': 'Invoice attached'},
                                    {'name': 'Date', 'value': 'Thu, 9 Apr 2026 12:00:00 +0000'},
                                ],
                                'parts': [
                                    {
                                        'filename': 'invoice.pdf',
                                        'mimeType': 'application/pdf',
                                        'body': {'attachmentId': 'att-1'},
                                    }
                                ],
                            }
                        }

                return FakeExecute()

            def attachments(self_inner):
                return FakeAttachments()

        class FakeUsers:
            def messages(self_inner):
                return FakeMessages()

        class FakeService:
            def users(self_inner):
                return FakeUsers()

        return FakeService()

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_process_gmail_message_returns_attachment_even_without_parser(self):
        attachment_data = base64.urlsafe_b64encode(b'%PDF-1.4 fake pdf').decode('utf-8')
        service = self._fake_service(attachment_data)

        with patch('invoices.services._selected_parser_for_vendor', return_value=None):
            result = process_gmail_message(service, 'gmail-msg-no-parser')

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['reason'], 'no parser configured')
        self.assertIn('attachment', result)
        self.assertEqual(result['attachment']['mimeType'], 'application/pdf')
        self.assertTrue(result['attachment']['url'].endswith('gmail-msg-no-parser_invoice.pdf'))

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_process_gmail_message_names_attachment_with_vendor_and_job(self):
        attachment_data = base64.urlsafe_b64encode(b'%PDF-1.4 fake pdf').decode('utf-8')
        service = self._fake_service(attachment_data)

        def fake_parser(_pdf_path):
            return {
                'invoice_number': 'INV-123',
                'cust_po': 'PO-456',
                'line_items': [{
                    'id': 'item-1',
                    'name': 'Parsed Item',
                    'job_id': 'JOB-123',
                    'job': 'Install',
                    'qty': '1',
                    'unit_price': 10,
                    'total_price': 10,
                }],
            }

        fake_parser.name = 'Parsed Vendor'

        with patch('invoices.services._selected_parser_for_vendor', return_value=fake_parser):
            result = process_gmail_message(service, 'gmail-msg-rename')

        self.assertEqual(result['status'], 'processed')
        self.assertEqual(
            result['attachment']['filename'],
            'gmail-msg-rename_Noparser_JOB-123_Install.pdf',
        )
        cache = EmailMessageCache.objects.get(email_id='gmail-msg-rename')
        self.assertEqual(cache.attachment_filename, 'gmail-msg-rename_Noparser_JOB-123_Install.pdf')
        self.assertEqual(cache.attachment_original_filename, 'invoice.pdf')
        self.assertTrue(
            os.path.exists(
                os.path.join(settings.MEDIA_ROOT, 'gmail-msg-rename_Noparser_JOB-123_Install.pdf')
            )
        )
        self.assertFalse(
            os.path.exists(os.path.join(settings.MEDIA_ROOT, 'gmail-msg-rename_invoice.pdf'))
        )


class ResetInvoiceDataTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name='Reset Vendor', invoice_type='pdf')
        self.contact = Contact.objects.create(
            vendor=self.vendor,
            name='Reset Contact',
            email='reset@example.com',
        )
        self.job = Job.objects.create(
            vendor=self.vendor,
            job_id='job-1',
            name='Reset Job',
        )
        self.item_type = ItemType.objects.create(name='Hardware')
        self.vendor_email = VendorEmail.objects.create(
            vendor=self.vendor,
            email='reset@example.com',
            is_primary=True,
        )
        self.email_cache = EmailMessageCache.objects.create(
            email_id='reset-msg-1',
            from_header='Reset Contact <reset@example.com>',
            subject='Reset Invoice',
            vendor=self.vendor,
        )
        self.automation_settings = InvoiceAutomationSettings.load()
        self.automation_settings.auto_process_enabled = True
        self.automation_settings.save(update_fields=['auto_process_enabled'])
        self.processed_email = ProcessedEmail.objects.create(
            email_id='reset-msg-1',
            status='processed',
            processed=timezone.now(),
            vendor=self.vendor,
            data={'foo': 'bar'},
        )
        self.invoice = Invoice.objects.create(
            vendor=self.vendor,
            contact=self.contact,
            source_email_id='reset-msg-1:1',
            status='processed',
        )
        self.inventory_item = InventoryItem.objects.create(
            vendor=self.vendor,
            item_type=self.item_type,
            item_key='reset-item',
            name='Reset Item',
            current_qty=3,
        )
        self.line_item = LineItem.objects.create(
            invoice=self.invoice,
            inventory_item=self.inventory_item,
            item_type=self.item_type,
            job=self.job,
            item_id='line-1',
            name='Reset Item',
            qty=3,
            unit_price=10,
            total_price=30,
        )

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_reset_invoice_data_clears_invoice_state_and_pdfs(self):
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        media_pdf_path = os.path.join(settings.MEDIA_ROOT, 'reset-msg-1_invoice.pdf')
        with open(media_pdf_path, 'wb') as handle:
            handle.write(b'%PDF-1.4 fake reset pdf')

        result = reset_invoice_data()

        self.assertFalse(result['remove_all'])
        self.assertEqual(result['deleted_counts']['email_message_cache'], 1)
        self.assertEqual(result['deleted_counts']['processed_emails'], 1)
        self.assertEqual(result['deleted_counts']['invoices'], 1)
        self.assertEqual(result['deleted_counts']['inventory_items'], 1)
        self.assertEqual(result['deleted_counts']['contacts'], 1)
        self.assertEqual(result['deleted_counts']['jobs'], 1)
        self.assertEqual(result['deleted_counts']['vendor_emails'], 1)
        self.assertNotIn('vendors', result['deleted_counts'])
        self.assertNotIn('item_types', result['deleted_counts'])
        self.assertEqual(EmailMessageCache.objects.count(), 0)
        self.assertEqual(ProcessedEmail.objects.count(), 0)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(LineItem.objects.count(), 0)
        self.assertEqual(InventoryItem.objects.count(), 0)
        self.assertEqual(ItemType.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(VendorEmail.objects.count(), 0)
        self.assertEqual(Vendor.objects.count(), 1)
        self.assertEqual(InvoiceAutomationSettings.objects.count(), 1)
        self.assertFalse(os.path.exists(media_pdf_path))

    def test_reset_invoice_data_can_remove_everything(self):
        result = reset_invoice_data(remove_all=True)

        self.assertTrue(result['remove_all'])
        self.assertEqual(result['deleted_counts']['vendors'], 1)
        self.assertEqual(result['deleted_counts']['item_types'], 1)
        self.assertEqual(result['deleted_counts']['automation_settings'], 1)
        self.assertEqual(EmailMessageCache.objects.count(), 0)
        self.assertEqual(ProcessedEmail.objects.count(), 0)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(LineItem.objects.count(), 0)
        self.assertEqual(InventoryItem.objects.count(), 0)
        self.assertEqual(Contact.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(VendorEmail.objects.count(), 0)
        self.assertEqual(Vendor.objects.count(), 0)
        self.assertEqual(ItemType.objects.count(), 0)
        self.assertEqual(InvoiceAutomationSettings.objects.count(), 0)

    def test_reset_invoice_data_view_preserves_references_by_default(self):
        response = self.client.post(
            '/api/automation/reset-data/',
            data=json.dumps({'remove_all': 'false'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['remove_all'])
        self.assertEqual(Vendor.objects.count(), 1)
        self.assertEqual(ItemType.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 0)

    def test_reset_invoice_data_view_can_remove_everything(self):
        response = self.client.post(
            '/api/automation/reset-data/',
            data=json.dumps({'remove_all': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['remove_all'])
        self.assertEqual(Vendor.objects.count(), 0)
        self.assertEqual(ItemType.objects.count(), 0)
        self.assertEqual(InvoiceAutomationSettings.objects.count(), 0)

    def test_reset_invoice_data_clears_inventory_with_out_of_range_decimals(self):
        """Regression: qty larger than DecimalField(12,4) must not block reset."""
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO invoices_inventoryitem (
                    vendor_id, item_key, item_id, name, description, unit,
                    current_qty, last_unit_price, last_total_price, metadata,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, '', '', %s, 0, 0, '{}', datetime('now'), datetime('now'))
                """,
                [self.vendor.id, 'bad-qty', 'BAD', 'Bad Qty', '15320149005'],
            )

        reset_invoice_data()

        self.assertEqual(InventoryItem.objects.count(), 0)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(LineItem.objects.count(), 0)
        self.assertEqual(ProcessedEmail.objects.count(), 0)


class AutomationSettingsTests(TestCase):
    def test_process_pending_gmail_invoices_returns_disabled_when_toggle_is_off(self):
        settings_obj = InvoiceAutomationSettings.load()
        settings_obj.auto_process_enabled = False
        settings_obj.last_processed_at = timezone.now() - timedelta(days=1)
        settings_obj.save(update_fields=['auto_process_enabled', 'last_processed_at'])
        original_last_processed_at = settings_obj.last_processed_at

        result = process_pending_gmail_invoices()

        settings_obj.refresh_from_db()
        self.assertEqual(result, {'status': 'disabled', 'processed': 0})
        self.assertEqual(settings_obj.last_processed_at, original_last_processed_at)

    @patch('invoices.services.get_gmail_service', return_value=object())
    @patch('invoices.services._list_message_ids', return_value=['msg-1', 'msg-2'])
    def test_process_pending_gmail_invoices_stops_when_disabled_mid_run(
        self,
        _list_message_ids,
        _get_gmail_service,
    ):
        settings_obj = InvoiceAutomationSettings.load()
        settings_obj.auto_process_enabled = True
        settings_obj.save(update_fields=['auto_process_enabled'])

        processed_messages = []

        def fake_process_gmail_message(_service, message_id):
            processed_messages.append(message_id)
            if message_id == 'msg-1':
                InvoiceAutomationSettings.objects.filter(pk=settings_obj.pk).update(auto_process_enabled=False)
            return {'status': 'processed'}

        with patch('invoices.services.process_gmail_message', side_effect=fake_process_gmail_message):
            result = process_pending_gmail_invoices()

        settings_obj.refresh_from_db()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['processed'], 1)
        self.assertEqual(processed_messages, ['msg-1'])
        self.assertFalse(settings_obj.auto_process_enabled)
        self.assertIsNone(settings_obj.last_processed_at)


class InvoiceReceiptStatusTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name='Receipt Vendor', invoice_type='pdf')
        self.invoice = Invoice.objects.create(
            vendor=self.vendor,
            source_email_id='receipt-msg-1',
            status='processed',
        )
        self.line_one = LineItem.objects.create(
            invoice=self.invoice,
            item_id='line-1',
            name='Item One',
            qty=1,
            unit_price=10,
            total_price=10,
        )
        self.line_two = LineItem.objects.create(
            invoice=self.invoice,
            item_id='line-2',
            name='Item Two',
            qty=1,
            unit_price=20,
            total_price=20,
        )

    def test_invoice_status_transitions_with_line_item_receipts(self):
        response = self.client.patch(
            f'/api/line-items/{self.line_one.id}/',
            data=json.dumps({'received': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'partially_received')

        response = self.client.patch(
            f'/api/line-items/{self.line_two.id}/',
            data=json.dumps({'received': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'received')

    def test_invoice_status_returns_to_processed_when_no_line_items_received(self):
        response = self.client.patch(
            f'/api/line-items/{self.line_one.id}/',
            data=json.dumps({'received': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.patch(
            f'/api/line-items/{self.line_one.id}/',
            data=json.dumps({'received': False}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'processed')


class GenericParserTests(TestCase):
    def test_defaults_to_generic_parser_when_vendor_parser_missing(self):
        vendor = Vendor.objects.create(name='Unknown Vendor', invoice_type='pdf')

        parser = _selected_parser_for_vendor(vendor)

        self.assertIsNotNone(parser)
        self.assertEqual(parser.__name__, 'parse_generic_invoice')

    def test_generic_parser_handles_fixture_pdfs(self):
        test_dir = os.path.join(settings.BASE_DIR, 'test')
        expected_vendors = {
            'quickbooks.pdf': 'Cache Valley Fire Protection',
            'quickbooks2.pdf': 'Sterling Medical, LLC',
            'generic.pdf': 'American Saw & Hammering',
        }

        for pdf_name, expected_vendor in expected_vendors.items():
            pdf_path = os.path.join(test_dir, pdf_name)
            raw = parse_generic_invoice(pdf_path)
            result = normalize_parser_output(raw, vendor_name=getattr(parse_generic_invoice, 'name', None))

            self.assertTrue(result['invoices'], pdf_name)
            self.assertTrue(result['invoices'][0]['line_items'], pdf_name)
            self.assertEqual(result['vendor_name'], expected_vendor, pdf_name)
            self.assertTrue(result['invoices'][0].get('invoice_number') or result['invoices'][0].get('invoice_total'), pdf_name)


class RugbyParserTests(TestCase):
    def test_rugby_parser_handles_invoice_and_credit_memo_fixtures(self):
        test_dir = os.path.join(settings.BASE_DIR, 'test')
        expected = {
            'rugby1.pdf': {
                'count': 2,
                'numbers': {'0013160191-001', '0013165944-001'},
                'credit_memo': False,
            },
            'rugby2.pdf': {
                'count': 1,
                'numbers': {'0013176411-001'},
                'credit_memo': True,
            },
            'rugby3.pdf': {
                'count': 3,
                'numbers': {'0013206840-001', '0013200907-001', '0013204590-001'},
                'credit_memo': False,
            },
            'rugby4.pdf': {
                'count': 1,
                'numbers': {'0013263145-001'},
                'credit_memo': False,
            },
        }

        for pdf_name, checks in expected.items():
            pdf_path = os.path.join(test_dir, pdf_name)
            raw = parse_rugby_invoice(pdf_path)
            result = normalize_parser_output(raw, vendor_name=getattr(parse_rugby_invoice, 'name', None))

            self.assertEqual(result['vendor_name'], 'Rugby ABP - Salt Lake City', pdf_name)
            self.assertEqual(len(result['invoices']), checks['count'], pdf_name)
            self.assertEqual(
                {invoice['invoice_number'] for invoice in result['invoices']},
                checks['numbers'],
                pdf_name,
            )
            for invoice in result['invoices']:
                self.assertTrue(invoice['line_items'], pdf_name)
                self.assertEqual(len(invoice['line_items']), 1, pdf_name)
                self.assertTrue(invoice['cust_po'], pdf_name)
                if checks['credit_memo']:
                    self.assertLess(float(invoice['invoice_total']), 0, pdf_name)
                else:
                    self.assertGreaterEqual(float(invoice['invoice_total']), 0, pdf_name)


class WeinigParserTests(TestCase):
    def test_weinig_parser_handles_invoice_and_statement_fixtures(self):
        test_dir = os.path.join(settings.BASE_DIR, 'test')
        expected = {
            'weinig1.pdf': {
                'vendor_name': 'Weinig Holz-Her USA, Inc.',
                'invoice_number': '1193770',
                'invoice_total': '621.15',
                'item_count': 11,
            },
            'weinig2.pdf': {
                'vendor_name': 'Weinig Holz-Her USA, Inc.',
                'invoice_number': '1193770',
                'invoice_total': '621.15',
                'item_count': 1,
            },
            'weinig3.pdf': {
                'vendor_name': 'WEINIG USA, Inc.',
                'invoice_number': '1199657',
                'invoice_total': '903.15',
                'item_count': 6,
            },
        }

        for pdf_name, checks in expected.items():
            pdf_path = os.path.join(test_dir, pdf_name)
            raw = parse_weinig_invoice(pdf_path)
            result = normalize_parser_output(raw, vendor_name=getattr(parse_weinig_invoice, 'name', None))

            self.assertEqual(result['vendor_name'], checks['vendor_name'], pdf_name)
            self.assertEqual(len(result['invoices']), 1, pdf_name)

            invoice = result['invoices'][0]
            self.assertEqual(invoice['invoice_number'], checks['invoice_number'], pdf_name)
            self.assertEqual(invoice['invoice_total'], checks['invoice_total'], pdf_name)
            self.assertTrue(invoice['line_items'], pdf_name)
            self.assertEqual(len(invoice['line_items']), checks['item_count'], pdf_name)
            self.assertTrue(invoice['cust_po'], pdf_name)


class IpacoParserTests(TestCase):
    def test_ipaco_parser_handles_invoice_and_statement_fixtures(self):
        test_dir = os.path.join(settings.BASE_DIR, 'test')
        expected = {
            'ipaco1.pdf': {
                'vendor_name': 'IPACO Inc.',
                'invoice_number': 'PS557500',
                'invoice_total': '25.11',
                'item_count': 2,
            },
            'ipaco2.pdf': {
                'vendor_name': 'IPACO Inc.',
                'invoice_count': 2,
                'invoice_totals': ['45.94', '41.18'],
            },
            'ipaco3.pdf': {
                'vendor_name': 'IPACO Inc.',
                'invoice_number': 'BL95086',
                'invoice_total': '4487.28',
                'item_count': 2,
            },
            'ipaco4.pdf': {
                'vendor_name': 'IPACO Inc.',
                'invoice_number': 'BL95383',
                'invoice_total': '561.18',
                'item_count': 3,
            },
            'ipaco5.pdf': {
                'vendor_name': 'IPACO Inc.',
                'invoice_number': 'PS550499',
                'invoice_total': '7.73',
                'item_count': 1,
            },
        }

        for pdf_name, checks in expected.items():
            pdf_path = os.path.join(test_dir, pdf_name)
            raw = parse_ipaco_invoice(pdf_path)
            result = normalize_parser_output(raw, vendor_name=getattr(parse_ipaco_invoice, 'name', None))

            self.assertEqual(result['vendor_name'], checks['vendor_name'], pdf_name)
            if 'invoice_count' in checks:
                self.assertEqual(len(result['invoices']), checks['invoice_count'], pdf_name)
                self.assertEqual(
                    [invoice['invoice_total'] for invoice in result['invoices']],
                    checks['invoice_totals'],
                    pdf_name,
                )
                continue

            self.assertEqual(len(result['invoices']), 1, pdf_name)
            invoice = result['invoices'][0]
            self.assertEqual(invoice['invoice_number'], checks['invoice_number'], pdf_name)
            self.assertEqual(invoice['invoice_total'], checks['invoice_total'], pdf_name)
            self.assertEqual(len(invoice['line_items']), checks['item_count'], pdf_name)
            self.assertTrue(invoice['cust_po'], pdf_name)


class SherwinParserTests(TestCase):
    def test_sherwin_parser_handles_invoice_fixtures(self):
        test_dir = os.path.join(settings.BASE_DIR, 'test')
        expected = {
            'sherwin1.pdf': {
                'invoice_number': '95512105181225',
                'invoice_total': '126.51',
                'item_count': 1,
            },
            'sherwin2.pdf': {
                'invoice_number': '0260-6',
                'invoice_total': '164.76',
                'item_count': 2,
            },
            'sherwin3.pdf': {
                'invoice_number': '08926126650126',
                'invoice_total': '164.76',
                'item_count': 2,
            },
            'sherwin4.pdf': {
                'invoice_number': '25714126650326',
                'invoice_total': '219.69',
                'item_count': 2,
            },
            'sherwin5.pdf': {
                'invoice_number': '36430126650526',
                'invoice_total': '109.84',
                'item_count': 2,
            },
        }

        for pdf_name, checks in expected.items():
            pdf_path = os.path.join(test_dir, pdf_name)
            raw = parse_sherwin_invoice(pdf_path)
            result = normalize_parser_output(raw, vendor_name=getattr(parse_sherwin_invoice, 'name', None))

            self.assertEqual(result['vendor_name'], 'The Sherwin-Williams Co.', pdf_name)
            self.assertEqual(len(result['invoices']), 1, pdf_name)
            invoice = result['invoices'][0]
            self.assertEqual(invoice['invoice_number'], checks['invoice_number'], pdf_name)
            self.assertEqual(invoice['invoice_total'], checks['invoice_total'], pdf_name)
            self.assertEqual(len(invoice['line_items']), checks['item_count'], pdf_name)
            self.assertTrue(invoice['cust_po'], pdf_name)


class YatesParserTests(TestCase):
    def test_yates_parser_handles_invoice_fixtures(self):
        test_dir = os.path.join(settings.BASE_DIR, 'test')
        expected = {
            'YATES_MOULDINGS1.pdf': {
                'invoice_number': '5225',
                'invoice_total': '2360.82',
                'invoice_due_date': '04/09/2026',
                'item_count': 1,
            },
            'YATES_MOULDINGS2.pdf': {
                'invoice_number': '5270',
                'invoice_total': '13956.00',
                'invoice_due_date': '05/01/2026',
                'item_count': 3,
            },
            'YATES_MOULDINGS3.pdf': {
                'invoice_number': '5271',
                'invoice_total': '7875.08',
                'invoice_due_date': '05/01/2026',
                'cust_po': 'FENNELL',
                'item_count': 3,
            },
            'YATES_MOULDINGS4.pdf': {
                'invoice_number': '5327',
                'invoice_total': '22009.40',
                'invoice_due_date': '06/05/2026',
                'item_count': 3,
            },
        }

        for pdf_name, checks in expected.items():
            pdf_path = os.path.join(test_dir, pdf_name)
            raw = parse_yates_mouldings_invoice(pdf_path)
            result = normalize_parser_output(
                raw,
                vendor_name=getattr(parse_yates_mouldings_invoice, 'name', None),
            )

            self.assertEqual(result['vendor_name'], 'Yates Mouldings', pdf_name)
            self.assertEqual(len(result['invoices']), 1, pdf_name)
            invoice = result['invoices'][0]
            self.assertEqual(invoice['invoice_number'], checks['invoice_number'], pdf_name)
            self.assertEqual(invoice['invoice_total'], checks['invoice_total'], pdf_name)
            self.assertEqual(invoice['invoice_due_date'], checks['invoice_due_date'], pdf_name)
            self.assertEqual(len(invoice['line_items']), checks['item_count'], pdf_name)
            if 'cust_po' in checks:
                self.assertEqual(invoice['cust_po'], checks['cust_po'], pdf_name)
            else:
                self.assertFalse(invoice['cust_po'], pdf_name)


class McMasterParserTests(TestCase):
    def test_mcmaster_parser_handles_invoice_fixtures(self):
        test_dir = os.path.join(settings.BASE_DIR, 'test')
        expected = {
            'McMaster_Carr1.PDF': {
                'invoice_number': '62816707',
                'invoice_total': '118.72',
                'item_count': 2,
            },
            'McMaster_Carr2.PDF': {
                'invoice_number': '63537683',
                'invoice_total': '78.03',
                'item_count': 4,
            },
            'McMaster_Carr3.PDF': {
                'invoice_number': '64677198',
                'invoice_total': '96.03',
                'item_count': 4,
            },
            'McMaster_Carr4.PDF': {
                'invoice_number': '65143433',
                'invoice_total': '327.23',
                'item_count': 1,
            },
            'McMaster_Carr5.PDF': {
                'invoice_number': '7920515',
                'invoice_total': '166.82',
                'item_count': 2,
            },
        }

        for pdf_name, checks in expected.items():
            pdf_path = os.path.join(test_dir, pdf_name)
            raw = parse_mcmaster_carr_invoice(pdf_path)
            result = normalize_parser_output(
                raw,
                vendor_name=getattr(parse_mcmaster_carr_invoice, 'name', None),
            )

            self.assertEqual(result['vendor_name'], 'McMaster-Carr Supply Company', pdf_name)
            self.assertEqual(len(result['invoices']), 1, pdf_name)
            invoice = result['invoices'][0]
            self.assertEqual(invoice['invoice_number'], checks['invoice_number'], pdf_name)
            self.assertEqual(invoice['invoice_total'], checks['invoice_total'], pdf_name)
            self.assertEqual(len(invoice['line_items']), checks['item_count'], pdf_name)
