from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Invoice
from .services import reset_processed_email_after_invoice_deleted


@receiver(pre_delete, sender=Invoice)
def reset_email_status_on_invoice_delete(sender, instance, **kwargs):
    reset_processed_email_after_invoice_deleted(instance)
