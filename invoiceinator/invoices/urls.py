from django.urls import path
from .views import list_invoice_emails, process_invoice_email, get_email_attachments

urlpatterns = [
    path('emails/', list_invoice_emails),
    path('process-email/', process_invoice_email),
    path('emails/<str:email_id>/attachments/', get_email_attachments),
]
