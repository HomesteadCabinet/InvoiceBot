from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    list_invoice_emails,
    process_invoice_email,
    get_email_attachments,
    VendorViewSet,
    test_parser
)

router = DefaultRouter()
router.register(r'vendors', VendorViewSet)

urlpatterns = [
    path('emails/', list_invoice_emails),
    path('process-email/', process_invoice_email),
    path('emails/<str:email_id>/attachments/', get_email_attachments),
    path('', include(router.urls)),
    path('test-parser/', test_parser),
]
