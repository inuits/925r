# Generated by Django 4.0 on 2023-09-14 12:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ninetofiver', '0095_attachment_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attachment',
            name='type',
            field=models.CharField(choices=[('n', 'None'), ('l', 'Leave attachment'), ('c', 'Contract attachment')], default='leave', max_length=15),
        ),
    ]
