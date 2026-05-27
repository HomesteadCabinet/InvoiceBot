from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0009_job_job_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemtype',
            name='icon',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
