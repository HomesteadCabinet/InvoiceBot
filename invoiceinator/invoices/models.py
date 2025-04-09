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

class Vendor(models.Model):
    name = models.CharField(max_length=255)
    invoice_type = models.CharField(max_length=255, choices=INVOICE_TYPE_CHOICES)
    spreadsheet_column_mapping = models.JSONField(null=True, blank=True, help_text="Column mapping for spreadsheet: {'invoice_number': 'A', 'date': 'B', 'total_amount': 'C'}")
    parser = models.CharField(max_length=255, null=True, blank=True, help_text="Parser method to use for extracting invoice data")

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
