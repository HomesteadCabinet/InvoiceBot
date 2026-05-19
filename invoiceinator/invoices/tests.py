from django.test import TestCase
from django.utils import timezone

from .models import Contact, InventoryItem, Invoice, Job, LineItem, ProcessedEmail, Vendor
from .services import (
    gmail_message_id_from_source_email_id,
    parsed_envelope_for_process_result,
    persist_parsed_invoices,
    reset_processed_email_after_invoice_deleted,
)


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

    def test_does_not_reset_while_sibling_invoice_remains(self):
        processed = self._create_processed_email()
        invoice_one = self._create_invoice(f'{self.message_id}:1')
        self._create_invoice(f'{self.message_id}:2')
        processed.invoice = invoice_one
        processed.save(update_fields=['invoice'])

        reset_processed_email_after_invoice_deleted(invoice_one)

        processed.refresh_from_db()
        self.assertEqual(processed.status, 'processed')

    def test_signal_resets_on_delete(self):
        processed = self._create_processed_email()
        invoice = self._create_invoice(f'{self.message_id}:1')

        invoice.delete()

        processed.refresh_from_db()
        self.assertEqual(processed.status, 'pending')


class PersistParsedInvoicesTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(
            name='Hafele America Co.',
            invoice_type='pdf',
        )

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
        self.assertEqual(invoice.line_items.count(), 1)

        contact = Contact.objects.get(vendor=self.vendor, email='orders@homestead.example')
        self.assertEqual(invoice.contact_id, contact.id)

        job = Job.objects.get(vendor=self.vendor, job_id='25668')
        self.assertEqual(job.name, 'LOHSS B1')
        line = LineItem.objects.get(invoice=invoice)
        self.assertEqual(line.job_id, job.id)

        inventory = InventoryItem.objects.get(vendor=self.vendor, item_key='546.63.116')
        self.assertEqual(line.inventory_item_id, inventory.id)

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
