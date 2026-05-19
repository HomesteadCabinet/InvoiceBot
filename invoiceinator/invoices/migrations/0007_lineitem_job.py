from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0006_invoice_received_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='lineitem',
            name='job',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
