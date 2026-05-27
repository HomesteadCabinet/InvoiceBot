from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0012_invoice_status_received_choices'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='contact',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='contact',
            constraint=models.UniqueConstraint(
                fields=('vendor', 'email'),
                condition=~Q(email=''),
                name='unique_vendor_contact_email_nonblank',
            ),
        ),
    ]
