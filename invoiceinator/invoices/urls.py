from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ContactViewSet,
    InvoiceViewSet,
    InventoryItemViewSet,
    automation_settings_view,
    google_auth_status,
    google_auth_url,
    google_disconnect,
    google_oauth_callback,
    export_invoices_xlsx,
    list_invoice_emails,
    flag_incorrect_parsing,
    process_invoice_email,
    reset_invoice_data_view,
    persist_parsed_invoice_view,
    process_invoices_now,
    ItemTypeViewSet,
    JobViewSet,
    LineItemViewSet,
    VendorViewSet,
    test_parser
)

router = DefaultRouter()
router.register(r'vendors', VendorViewSet)
router.register(r'item-types', ItemTypeViewSet, basename='item-type')
router.register(r'jobs', JobViewSet, basename='job')
router.register(r'contacts', ContactViewSet, basename='contact')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'inventory-items', InventoryItemViewSet, basename='inventory-item')
router.register(r'line-items', LineItemViewSet, basename='line-item')

urlpatterns = [
    path('automation/settings/', automation_settings_view),
    path('automation/process-now/', process_invoices_now),
    path('export/xlsx/', export_invoices_xlsx),
    path('google/auth-url/', google_auth_url),
    path('google/callback/', google_oauth_callback, name='google_oauth_callback'),
    path('google/status/', google_auth_status),
    path('google/disconnect/', google_disconnect),
    path('emails/', list_invoice_emails),
    path('process-email/', process_invoice_email),
    path('emails/flag-incorrect-parsing/', flag_incorrect_parsing),
    path('automation/reset-data/', reset_invoice_data_view),
    path('persist-parsed/', persist_parsed_invoice_view),
    path('', include(router.urls)),
    path('test-parser/', test_parser),
]
