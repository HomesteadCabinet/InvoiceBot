from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0008_job_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='job_id',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Business job identifier (e.g. numeric PO from Hafele line items).',
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name='job',
            name='name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.RemoveField(
            model_name='job',
            name='customer_po',
        ),
        migrations.AlterUniqueTogether(
            name='job',
            unique_together={('vendor', 'job_id', 'name')},
        ),
        migrations.AlterModelOptions(
            name='job',
            options={'ordering': ['job_id', 'name']},
        ),
    ]
