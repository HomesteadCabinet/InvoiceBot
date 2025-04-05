from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processed', 'Processed'),
    ('error', 'Error'),
]

INVOICE_TYPE_CHOICES = [
    ('pdf', 'PDF'),
]

DATA_TYPE_CHOICES = [
    ('text', 'Text'),
    ('number', 'Number'),
    ('date', 'Date'),
    ('currency', 'Currency'),
    ('email', 'Email'),
    ('phone', 'Phone'),
    ('line_items', 'Line Items'),  # Add this
]

LOCATION_TYPE_CHOICES = [
    ('coordinates', 'Coordinates'),
    ('keyword', 'Keyword'),
    ('regex', 'Regular Expression'),
    ('table', 'Table'),
    ('header', 'Header'),
]


class DataRule(models.Model):
    vendor = models.ForeignKey('Vendor', on_delete=models.CASCADE, related_name='data_rules')
    field_name = models.CharField(max_length=255, help_text="Name of the field to extract")
    data_type = models.CharField(max_length=50, choices=DATA_TYPE_CHOICES)
    location_type = models.CharField(max_length=50, choices=LOCATION_TYPE_CHOICES)

    # Location parameters based on location_type
    coordinates = models.JSONField(null=True, blank=True, help_text="For coordinate-based extraction: {'x': float, 'y': float, 'width': float, 'height': float}")
    keyword = models.CharField(max_length=255, null=True, blank=True, help_text="Keyword to search for")
    regex_pattern = models.CharField(max_length=255, null=True, blank=True, help_text="Regular expression pattern")
    table_config = models.JSONField(null=True, blank=True,
        help_text="For table-based extraction: {'start_row_after_header': int, 'item_columns': key/value pairs, 'header_text': str}",
        default=dict
    )

    # Validation rules
    required = models.BooleanField(default=True)
    # validation_regex = models.CharField(max_length=255, null=True, blank=True, help_text="Regex pattern for validation")
    # min_value = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    # max_value = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])

    # Processing rules
    pre_processing = models.JSONField(null=True, blank=True, help_text="Pre-processing steps: {'remove_spaces': bool, 'to_uppercase': bool, etc.}")
    post_processing = models.JSONField(null=True, blank=True, help_text="Post-processing steps: {'format_date': str, 'round_decimals': int, etc.}")

    # Metadata
    description = models.TextField(blank=True, help_text="Description of what this rule extracts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    bbox = models.JSONField(null=True, blank=True, help_text="Bounding box for the rule")

    def __str__(self):
        return f"{self.vendor.name} - {self.field_name}"

    class Meta:
        unique_together = ['vendor', 'field_name']


class Vendor(models.Model):
    name = models.CharField(max_length=255)
    invoice_type = models.CharField(max_length=255, choices=INVOICE_TYPE_CHOICES)
    spreadsheet_column_mapping = models.JSONField(null=True, blank=True, help_text="Column mapping for spreadsheet: {'invoice_number': 'A', 'date': 'B', 'total_amount': 'C'}")

    def __str__(self):
        return self.name


class ProcessedEmail(models.Model):
    email_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=255, choices=STATUS_CHOICES, default='pending')
    processed = models.DateTimeField(null=True, blank=True)
    data = models.JSONField(default=dict, help_text="Data extracted from the email")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True)

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
