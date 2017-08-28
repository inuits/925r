# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-06-12 12:06
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ninetofiver', '0035_whereabout'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='timesheet',
            name='closed',
        ),
        migrations.AddField(
            model_name='timesheet',
            name='status',
            field=models.CharField(choices=[('CLOSED', 'Closed'), ('ACTIVE', 'Active'), ('PENDING', 'Pending')], default='ACTIVE', max_length=16),
        ),
    ]