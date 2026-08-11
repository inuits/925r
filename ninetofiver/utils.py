"""Utils."""
import copy
import datetime
import os
from calendar import monthrange
from importlib import import_module

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail as base_send_mail
from django.db.models import Q
from django.template.loader import render_to_string
from import_export.widgets import ManyToManyWidget

DEFAULT_DJANGO_ENVIRONMENT = 'dev'


def get_django_environment():
    """Get the django environment."""
    return os.getenv('ENVIRONMENT', DEFAULT_DJANGO_ENVIRONMENT)


def get_django_configuration():
    """Get the django configuration name based on the current environment."""
    env = get_django_environment()

    env_map = {
        'dev': 'Dev',
        'staging': 'Stag',
        'demo': 'Demo',
        'production': 'Prod',
    }

    if env not in env_map:
        # 'dev' (the default used when ENVIRONMENT is genuinely unset) is an explicit key
        # in env_map above, so we only get here when ENVIRONMENT was explicitly set to a
        # value we don't recognize. Fail loudly instead of silently booting with Dev's
        # debug settings.
        raise ImproperlyConfigured(
            "Unrecognized ENVIRONMENT value '%s'. Valid options are: %s."
            % (env, ', '.join(sorted(env_map.keys())))
        )

    return env_map[env]


def str_import(string):
    """Import a class from a string."""
    module, attr = string.rsplit('.', maxsplit=1)
    module = import_module(module)
    attr = getattr(module, attr)

    return attr


def merge_dicts(*dicts):
    """Merge two dicts."""
    result = {}
    [result.update(x) for x in dicts]

    return result


def days_in_month(year, month):
    """Get the amount of days in a month."""
    return monthrange(year, month)[1]


def month_date_range(year, month):
    """Get the date range for the given month."""
    from_date = datetime.date.today().replace(year=year, month=month, day=1)
    until_date = from_date.replace() + relativedelta(months=1) - relativedelta(days=1)
    return [from_date, until_date]


def dates_in_range(from_date, until_date):
    """Get all dates for the given date range."""
    dates = []
    current_date = copy.deepcopy(from_date)
    while current_date.strftime('%Y%m%d') <= until_date.strftime('%Y%m%d'):
        dates.append(copy.deepcopy(current_date))
        current_date += relativedelta(days=1)
    return dates


def hours_to_days(hours, rounded=True):
    """Convert hours to days."""
    if rounded:
        return round(hours / 8, 2)
    else:
        return hours / 8


def format_duration(hours):
    """Format duration as a string."""
    if hours is None:
        return hours
    return '%(amount).2fh (%(days).2fd)' % {'amount': hours, 'days': hours_to_days(hours)}


def send_mail(recipients, subject, template, context={}):
    """Send a mail from a template to the given recipients."""
    from ninetofiver.settings import DEFAULT_FROM_EMAIL
    from django_settings_export import _get_exported_settings

    if type(recipients) not in [list, tuple]:
        recipients = [recipients]

    context['settings'] = _get_exported_settings()
    message = render_to_string(template, context=context)

    base_send_mail(
        subject,
        '',
        DEFAULT_FROM_EMAIL,
        recipients,
        fail_silently=False,
        html_message=message
    )


def get_users_with_permission(permission):
    """Get a list of all users with a given permission."""
    from django.contrib.auth import models as auth_models

    users = (auth_models.User.objects
             .filter(Q(is_staff=True),
                     Q(is_superuser=True) |
                     Q(groups__permissions__codename=permission) |
                     Q(user_permissions__codename=permission))
             .distinct())
    return users


class IntelligentManyToManyWidget(ManyToManyWidget):
    """
    Same as parent widget, but you can pass lookup key.
    Behaves same if passed a Model field, but if it is method, it will try to execute it.
    """

    def __init__(self, model, separator=None, field=None, lookup=None, *args, **kwargs):
        self.lookup = lookup
        super(IntelligentManyToManyWidget, self).__init__(model, separator, field, *args, **kwargs)

    def render(self, value, obj=None):
        ids = []
        lookup_field = self.lookup or self.field
        for obj in value.all():
            resolved_field = getattr(obj, lookup_field)
            if callable(resolved_field):
                ids.append(resolved_field())
            else:
                ids.append(resolved_field)
        return self.separator.join(ids)


class AvailabilityInfo(object):
    def __init__(self):
        self.day_tags = []
        self.leave_dates = []

    def add_tag(self, tag):
        self.day_tags.append(tag)
