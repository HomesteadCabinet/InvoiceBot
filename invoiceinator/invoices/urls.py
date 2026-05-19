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
    process_invoice_email,
    process_invoices_now,
    ItemTypeViewSet,
    LineItemViewSet,
    VendorViewSet,
    test_parser
)

router = DefaultRouter()
router.register(r'vendors', VendorViewSet)
router.register(r'item-types', ItemTypeViewSet, basename='item-type')
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
    path('', include(router.urls)),
    path('test-parser/', test_parser),
]
