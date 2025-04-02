from django.contrib import admin
from .models import ProcessedEmail, Vendor


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
