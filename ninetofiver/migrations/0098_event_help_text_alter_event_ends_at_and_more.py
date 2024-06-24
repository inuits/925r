# Generated by Django 4.0 on 2024-06-24 08:29

import datetime
from django.db import migrations, models
import recurrence.fields


class Migration(migrations.Migration):

    dependencies = [
        ('ninetofiver', '0096_event'),
        ('ninetofiver', '0097_quote'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='help_text',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='ends_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='starts_at',
            field=models.DateTimeField(default=datetime.datetime.now),
        ),
        migrations.AlterField(
            model_name='quote',
            name='recurrences',
            field=recurrence.fields.RecurrenceField(blank=True, help_text='RDATE:YYYYMMDDTHHMMSSZ\nhttps://jkbrzt.github.io/rrule/', null=True),
        ),
    ]