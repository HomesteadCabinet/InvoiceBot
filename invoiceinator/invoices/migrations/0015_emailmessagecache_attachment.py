from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0014_emailmessagecache'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailmessagecache',
            name='attachment_filename',
            field=models.CharField(blank=True, default='', max_length=512),
        ),
        migrations.AddField(
            model_name='emailmessagecache',
            name='attachment_original_filename',
            field=models.CharField(blank=True, default='', max_length=512),
        ),
        migrations.AddField(
            model_name='emailmessagecache',
            name='attachment_mime_type',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
