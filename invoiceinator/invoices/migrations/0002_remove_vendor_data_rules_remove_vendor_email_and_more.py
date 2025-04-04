# Generated by Django 5.2 on 2025-04-04 19:42

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='vendor',
            name='data_rules',
        ),
        migrations.RemoveField(
            model_name='vendor',
            name='email',
        ),
        migrations.AddField(
            model_name='processedemail',
            name='vendor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='invoices.vendor'),
        ),
        migrations.AddField(
            model_name='vendor',
            name='spreadsheet_column_mapping',
            field=models.JSONField(blank=True, help_text="Column mapping for spreadsheet: {'invoice_number': 'A', 'date': 'B', 'total_amount': 'C'}", null=True),
        ),
        migrations.AlterField(
            model_name='processedemail',
            name='data',
            field=models.JSONField(default=dict, help_text='Data extracted from the email'),
        ),
        migrations.AlterField(
            model_name='processedemail',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('processed', 'Processed'), ('error', 'Error')], default='pending', max_length=255),
        ),
        migrations.AlterField(
            model_name='vendor',
            name='invoice_type',
            field=models.CharField(choices=[('pdf', 'PDF')], max_length=255),
        ),
        migrations.CreateModel(
            name='DataRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field_name', models.CharField(help_text='Name of the field to extract', max_length=255)),
                ('data_type', models.CharField(choices=[('text', 'Text'), ('number', 'Number'), ('date', 'Date'), ('currency', 'Currency'), ('email', 'Email'), ('phone', 'Phone'), ('line_items', 'Line Items')], max_length=50)),
                ('location_type', models.CharField(choices=[('coordinates', 'Coordinates'), ('keyword', 'Keyword'), ('regex', 'Regular Expression'), ('table', 'Table'), ('header', 'Header')], max_length=50)),
                ('coordinates', models.JSONField(blank=True, help_text="For coordinate-based extraction: {'x': float, 'y': float, 'width': float, 'height': float}", null=True)),
                ('keyword', models.CharField(blank=True, help_text='Keyword to search for', max_length=255, null=True)),
                ('regex_pattern', models.CharField(blank=True, help_text='Regular expression pattern', max_length=255, null=True)),
                ('table_config', models.JSONField(blank=True, default=dict, help_text="For table-based extraction: {'start_row_after_header': int, 'item_columns': key/value pairs, 'header_text': str}", null=True)),
                ('required', models.BooleanField(default=True)),
                ('pre_processing', models.JSONField(blank=True, help_text="Pre-processing steps: {'remove_spaces': bool, 'to_uppercase': bool, etc.}", null=True)),
                ('post_processing', models.JSONField(blank=True, help_text="Post-processing steps: {'format_date': str, 'round_decimals': int, etc.}", null=True)),
                ('description', models.TextField(blank=True, help_text='Description of what this rule extracts')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('bbox', models.JSONField(blank=True, help_text='Bounding box for the rule', null=True)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='data_rules', to='invoices.vendor')),
            ],
            options={
                'unique_together': {('vendor', 'field_name')},
            },
        ),
        migrations.CreateModel(
            name='VendorEmail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('is_primary', models.BooleanField(default=False)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='emails', to='invoices.vendor')),
            ],
            options={
                'unique_together': {('vendor', 'email')},
            },
        ),
    ]
