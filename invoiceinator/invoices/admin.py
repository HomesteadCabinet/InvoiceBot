from django.contrib import admin
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
)


@admin.register(ProcessedEmail)
class ProcessedEmailAdmin(admin.ModelAdmin):
    list_display = ('email_id', 'status', 'processed')
    list_filter = ('status',)
    search_fields = ('email_id',)
    readonly_fields = ('processed',)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'invoice_type')
    list_filter = ('invoice_type',)
    search_fields = ('name',)


@admin.register(ItemType)
class ItemTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'color')
    search_fields = ('name',)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('job_id', 'name', 'vendor', 'updated_at')
    list_filter = ('vendor',)
    search_fields = ('job_id', 'name', 'notes')


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor', 'email', 'is_primary')
    list_filter = ('vendor', 'is_primary')
    search_fields = ('name', 'email', 'phone')


@admin.register(InvoiceAutomationSettings)
class InvoiceAutomationSettingsAdmin(admin.ModelAdmin):
    list_display = ('auto_process_enabled', 'max_email_age_days', 'poll_interval_seconds', 'last_processed_at', 'updated_at')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'vendor', 'contact', 'status', 'received_at', 'processed_at', 'created_at')
    list_filter = ('status', 'vendor')
    search_fields = ('invoice_number', 'source_email_id', 'source_email_subject')


@admin.register(LineItem)
class LineItemAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'item_id', 'name', 'job', 'item_type', 'qty', 'total_price')
    search_fields = ('item_id', 'name', 'description')


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('item_key', 'name', 'vendor', 'item_type', 'current_qty', 'last_invoiced_at')
    search_fields = ('item_key', 'item_id', 'name')
