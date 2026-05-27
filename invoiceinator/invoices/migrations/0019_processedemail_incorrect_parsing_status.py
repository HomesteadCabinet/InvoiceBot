from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0018_itemtype_parent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processedemail',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('processed', 'Processed'),
                    ('error', 'Error'),
                    ('incorrect_parsing', 'Incorrect parsing'),
                ],
                default='pending',
                max_length=255,
            ),
        ),
    ]
