from django.db import migrations, models
import django.db.models.deletion


def migrate_line_item_job_strings(apps, schema_editor):
    LineItem = apps.get_model('invoices', 'LineItem')
    Job = apps.get_model('invoices', 'Job')
    Invoice = apps.get_model('invoices', 'Invoice')

    for line_item in LineItem.objects.exclude(job_legacy='').iterator():
        name = (line_item.job_legacy or '').strip()
        if not name:
            continue
        vendor_id = None
        if line_item.invoice_id:
            invoice = Invoice.objects.filter(pk=line_item.invoice_id).only('vendor_id').first()
            vendor_id = invoice.vendor_id if invoice else None
        job, _ = Job.objects.get_or_create(vendor_id=vendor_id, name=name)
        line_item.job_id = job.id
        line_item.save(update_fields=['job_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0007_lineitem_job'),
    ]

    operations = [
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('customer_po', models.CharField(blank=True, default='', help_text='Optional PO number associated with this job.', max_length=255)),
                ('notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('vendor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs', to='invoices.vendor')),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('vendor', 'name')},
            },
        ),
        migrations.RenameField(
            model_name='lineitem',
            old_name='job',
            new_name='job_legacy',
        ),
        migrations.AddField(
            model_name='lineitem',
            name='job',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='line_items',
                to='invoices.job',
            ),
        ),
        migrations.RunPython(migrate_line_item_job_strings, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='lineitem',
            name='job_legacy',
        ),
    ]
