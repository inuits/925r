# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-09-29 08:20
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ninetofiver', '0047_contract_external_only'),
    ]

    operations = [
        migrations.AlterField(
            model_name='performance',
            name='contract',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='ninetofiver.Contract'),
        ),
    ]