# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-09-22 11:23
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ninetofiver', '0046_auto_20170912_1445'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='external_only',
            field=models.BooleanField(default=False),
        ),
    ]