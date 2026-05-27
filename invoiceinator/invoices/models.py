from django.db import models
from django.core.validators import MinValueValidator
from django.db.models import Q

STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processed', 'Processed'),
    ('error', 'Error'),
    ('incorrect_parsing', 'Incorrect parsing'),
]

INVOICE_TYPE_CHOICES = [
    ('pdf', 'PDF'),
]

INVOICE_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processed', 'Processed'),
    ('partially_received', 'Partially Received'),
    ('received', 'Received'),
    ('error', 'Error'),
]


class Vendor(models.Model):
    ignore = models.BooleanField(default=False)
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='vendor_logos/', null=True, blank=True)
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=255, blank=True, default='')
    state = models.CharField(max_length=255, blank=True, default='')
    zip_code = models.CharField(max_length=255, blank=True, default='')
    country = models.CharField(max_length=255, blank=True, default='')
    phone = models.CharField(max_length=255, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    website = models.URLField(blank=True, default='')
    invoice_type = models.CharField(max_length=255, choices=INVOICE_TYPE_CHOICES)
    parser = models.CharField(max_length=255, null=True, blank=True, help_text="Parser method to use for extracting invoice data")

    def __str__(self):
        return self.name


def exclude_ignored_vendor_relations(queryset, vendor_lookup='vendor'):
    """Exclude rows linked to vendors with ``ignore=True``."""
    return queryset.exclude(**{f'{vendor_lookup}__ignore': True})


class ItemType(models.Model):
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    color = models.CharField(max_length=32, blank=True, default='')
    icon = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['parent', 'name'],
                name='unique_itemtype_parent_name',
            ),
        ]
        ordering = ['name']

    def __str__(self):
        return self.get_full_path()

    def get_full_path(self):
        names = []
        node = self
        seen_ids = set()
        while node is not None:
            if node.pk and node.pk in seen_ids:
                break
            if node.pk:
                seen_ids.add(node.pk)
            names.append(node.name)
            node = node.parent if node.parent_id else None
        return ' › '.join(reversed(names))


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
        constraints = [
            models.UniqueConstraint(
                fields=['vendor', 'email'],
                condition=~Q(email=''),
                name='unique_vendor_contact_email_nonblank',
            ),
        ]

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
    received = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
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


class EmailMessageCache(models.Model):
    email_id = models.CharField(max_length=255, unique=True)
    thread_id = models.CharField(max_length=255, blank=True, default='')
    snippet = models.TextField(blank=True, default='')
    from_header = models.CharField(max_length=512, blank=True, default='')
    subject = models.CharField(max_length=512, blank=True, default='')
    date_header = models.CharField(max_length=255, blank=True, default='')
    attachment_count = models.PositiveIntegerField(default=0)
    attachment_filename = models.CharField(max_length=512, blank=True, default='')
    attachment_original_filename = models.CharField(max_length=512, blank=True, default='')
    attachment_mime_type = models.CharField(max_length=255, blank=True, default='')
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    raw_headers = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_seen_at', '-updated_at']

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
