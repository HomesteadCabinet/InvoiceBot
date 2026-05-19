from django.db import models
from django.core.validators import MinValueValidator

STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processed', 'Processed'),
    ('error', 'Error'),
]

INVOICE_TYPE_CHOICES = [
    ('pdf', 'PDF'),
]

INVOICE_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processed', 'Processed'),
    ('error', 'Error'),
]

class Vendor(models.Model):
    name = models.CharField(max_length=255)
    invoice_type = models.CharField(max_length=255, choices=INVOICE_TYPE_CHOICES)
    spreadsheet_column_mapping = models.JSONField(null=True, blank=True, help_text="Column mapping for spreadsheet: {'invoice_number': 'A', 'date': 'B', 'total_amount': 'C'}")
    parser = models.CharField(max_length=255, null=True, blank=True, help_text="Parser method to use for extracting invoice data")

    def __str__(self):
        return self.name


class ItemType(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default='')
    color = models.CharField(max_length=32, blank=True, default='')

    def __str__(self):
        return self.name


class Job(models.Model):
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jobs',
    )
    job_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Business job identifier (e.g. numeric PO from Hafele line items).',
    )
    name = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['vendor', 'job_id', 'name']
        ordering = ['job_id', 'name']

    def __str__(self):
        label = self.job_id or self.name or 'Job'
        if self.name and self.job_id and self.name != self.job_id:
            label = f"{self.job_id} {self.name}"
        if self.vendor:
            return f"{label} ({self.vendor.name})"
        return label


class Contact(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='contacts', null=True, blank=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=64, blank=True, default='')
    title = models.CharField(max_length=255, blank=True, default='')
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ['vendor', 'email']

    def __str__(self):
        if self.vendor:
            return f"{self.name} ({self.vendor.name})"
        return self.name


class InvoiceAutomationSettings(models.Model):
    auto_process_enabled = models.BooleanField(default=False)
    max_email_age_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        help_text="Skip Gmail messages older than this many days.",
    )
    poll_interval_seconds = models.PositiveIntegerField(
        default=60,
        validators=[MinValueValidator(10)],
        help_text="How often the background worker checks for new invoices.",
    )
    last_processed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Invoice automation settings"

    @classmethod
    def load(cls):
        instance, _created = cls.objects.get_or_create(pk=1)
        return instance


class Invoice(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True)
    source_email_id = models.CharField(max_length=255, unique=True)
    source_email_subject = models.CharField(max_length=512, blank=True, default='')
    source_email_from = models.CharField(max_length=512, blank=True, default='')
    source_email_date = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the invoice email was received or ingested.",
    )
    invoice_number = models.CharField(max_length=255, blank=True, default='')
    invoice_date = models.DateField(null=True, blank=True)
    ship_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    customer_po = models.CharField(max_length=255, blank=True, default='')
    invoice_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=255, choices=INVOICE_STATUS_CHOICES, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.invoice_number or self.source_email_id


class InventoryItem(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    item_type = models.ForeignKey(ItemType, on_delete=models.SET_NULL, null=True, blank=True)
    item_key = models.CharField(max_length=255)
    item_id = models.CharField(max_length=255, blank=True, default='')
    name = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')
    unit = models.CharField(max_length=64, blank=True, default='')
    current_qty = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    last_unit_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    last_total_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    last_invoiced_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['vendor', 'item_key']

    def __str__(self):
        return self.name or self.item_key


class LineItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='line_items',
    )
    item_type = models.ForeignKey(ItemType, on_delete=models.SET_NULL, null=True, blank=True)
    job = models.ForeignKey(
        Job,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='line_items',
    )
    item_id = models.CharField(max_length=255, blank=True, default='')
    name = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')
    qty = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    unit = models.CharField(max_length=64, blank=True, default='')
    unit_price = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    width = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    length = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    height = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.item_id or self.name or 'Line Item'}"


class ProcessedEmail(models.Model):
    email_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=255, choices=STATUS_CHOICES, default='pending')
    processed = models.DateTimeField(null=True, blank=True)
    data = models.JSONField(default=dict, help_text="Data extracted from the email")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.email_id


class VendorEmail(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='emails')
    email = models.EmailField(unique=True)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.vendor.name} - {self.email}"

    class Meta:
        unique_together = ['vendor', 'email']
