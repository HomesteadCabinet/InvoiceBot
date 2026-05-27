from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0011_lineitem_notes_lineitem_received'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('processed', 'Processed'), ('partially_received', 'Partially Received'), ('received', 'Received'), ('error', 'Error')], default='pending', max_length=255),
        ),
    ]
