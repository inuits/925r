import django_countries.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ninetofiver', '0099_supportcontract_complexity'),
    ]

    operations = [
        migrations.AddField(
            model_name='leavetype',
            name='auto_approve',
            field=models.BooleanField(
                default=False,
                help_text='Bypass the approval flow and mark leaves of this type as approved immediately on save.',
                verbose_name='Auto approve',
            ),
        ),
        migrations.AddField(
            model_name='leavetype',
            name='message',
            field=models.TextField(
                blank=True,
                null=True,
                max_length=255,
                help_text='Trusted HTML shown to the user when this leave type is selected '
                          '(e.g. a link to an external booking system).',
            ),
        ),
        migrations.AddField(
            model_name='leavetype',
            name='visible_for_countries',
            field=django_countries.fields.CountryField(
                blank=True,
                max_length=746,
                multiple=True,
                verbose_name='Show leaves to those user countries',
                help_text='Only users from these countries see this leave type. '
                          'Leave empty to show it to everyone.',
            ),
        ),
    ]
