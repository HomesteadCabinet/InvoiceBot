from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0013_contact_multiple_contacts'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailMessageCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_id', models.CharField(max_length=255, unique=True)),
                ('thread_id', models.CharField(blank=True, default='', max_length=255)),
                ('snippet', models.TextField(blank=True, default='')),
                ('from_header', models.CharField(blank=True, default='', max_length=512)),
                ('subject', models.CharField(blank=True, default='', max_length=512)),
                ('date_header', models.CharField(blank=True, default='', max_length=255)),
                ('attachment_count', models.PositiveIntegerField(default=0)),
                ('raw_headers', models.JSONField(blank=True, default=dict)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('vendor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='invoices.vendor')),
            ],
            options={
                'ordering': ['-last_seen_at', '-updated_at'],
            },
        ),
    ]
