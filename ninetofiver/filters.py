"""Filters."""
import logging

import django_filters
from django.contrib.admin import widgets as admin_widgets
from django.contrib.auth import models as auth_models
from django_select2 import forms as select2_widgets
from django.utils.translation import ugettext_lazy as _
from django_filters.rest_framework import FilterSet

from ninetofiver import models

logger = logging.getLogger(__name__)


# Filters for reports
class AdminReportTimesheetContractOverviewFilter(FilterSet):
    """Timesheet contract overview admin report filter."""
    performance__contract = (django_filters.ModelMultipleChoiceFilter(
        label='Contract',
        queryset=(models.Contract.objects.filter(active=True).select_related('customer')),
        widget=select2_widgets.Select2MultipleWidget,
    ))
    performance__contract__polymorphic_ctype__model = (django_filters.MultipleChoiceFilter(
        label='Contract type',
        choices=[
            ('projectcontract', _('Project')),
            ('consultancycontract', _('Consultancy')),
            ('supportcontract', _('Support'))],
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    performance__contract__customer = (django_filters.ModelMultipleChoiceFilter(
        label='Contract customer',
        queryset=models.Company.objects.filter(),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    performance__contract__company = (django_filters.ModelMultipleChoiceFilter(
        label='Contract company',
        queryset=models.Company.objects.filter(internal=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    performance__contract__contract_groups = (django_filters.ModelMultipleChoiceFilter(
        label='Contract group',
        queryset=models.ContractGroup.objects.all(),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    month = django_filters.MultipleChoiceFilter(
        choices=lambda: [[x + 1, x + 1] for x in range(12)],
        widget=select2_widgets.Select2MultipleWidget,
    )
    year = django_filters.MultipleChoiceFilter(
        choices=lambda: [[x, x] for x in (
            models.Timesheet.objects.values_list('year', flat=True).order_by('year').distinct()
        )],
        widget=select2_widgets.Select2MultipleWidget,
    )
    user = django_filters.ModelMultipleChoiceFilter(
        queryset=auth_models.User.objects.filter(is_active=True),
        widget=select2_widgets.Select2MultipleWidget,
    )
    user__employmentcontract__company = django_filters.ModelChoiceFilter(
        label='User company',
        queryset=models.Company.objects.filter(internal=True),
        distinct=True,
        widget=select2_widgets.Select2Widget,
        # NOTE (to my future self):
        # if you want to use Django (>=2.0) autocomplete_select feature use the widget like below:
        # widget=admin_widgets.AutocompleteSelect(models.EmploymentContract.company.field, admin.site, attrs=ATTRS_FIX),
        # It is needed to add search_fields in admin.py to the Proper model and field.
        # This will use Select2 integrated with django with lazy loading.
    )

    class Meta:
        model = models.Timesheet
        fields = {
            'performance__contract': ['exact'],
            'performance__contract__polymorphic_ctype__model': ['exact'],
            'performance__contract__customer': ['exact'],
            'performance__contract__company': ['exact'],
            'performance__contract__contract_groups': ['exact'],
            'month': ['exact'],
            'year': ['exact'],
            'user': ['exact'],
            'user__employmentcontract__company': ['exact'],
            'status': ['exact'],
        }


class AdminReportTimesheetOverviewFilter(FilterSet):
    """Timesheet overview admin report filter."""
    user = django_filters.ModelChoiceFilter(
        queryset=auth_models.User.objects.filter(is_active=True),
        widget=select2_widgets.Select2Widget,
    )
    user__employmentcontract__company = django_filters.ModelChoiceFilter(
        label='Company',
        queryset=models.Company.objects.filter(internal=True),
        distinct=True,
        widget=select2_widgets.Select2Widget,
    )
    user__employmentcontract = django_filters.ModelChoiceFilter(
        label='Contract Type',
        queryset=models.EmploymentContractType.objects.filter(),
        distinct=True,
        widget=select2_widgets.Select2Widget,
    )
    year = django_filters.ChoiceFilter(
        choices=lambda: [[x, x] for x in (
            models.Timesheet.objects.values_list('year', flat=True).order_by('year').distinct()
        )],
        widget=select2_widgets.Select2Widget,
    )
    month = django_filters.ChoiceFilter(
        choices=lambda: [[x + 1, x + 1] for x in range(12)],
        widget=select2_widgets.Select2Widget,
    )

    class Meta:
        model = models.Timesheet
        fields = {
            'user': ['exact'],
            'user__employmentcontract__company': ['exact'],
            'user__employmentcontract': ['exact'],
            'status': ['exact'],
            'year': ['exact'],
            'month': ['exact'],
        }


class AdminReportUserRangeInfoFilter(FilterSet):
    """User range info admin report filter."""
    user = django_filters.ModelChoiceFilter(
        queryset=auth_models.User.objects.filter(is_active=True),
        widget=select2_widgets.Select2Widget,
    )
    from_date = django_filters.DateFilter(label='From', widget=admin_widgets.AdminDateWidget())
    until_date = django_filters.DateFilter(label='Until', widget=admin_widgets.AdminDateWidget())

    class Meta:
        model = models.Timesheet
        fields = {
            'user': ['exact'],
        }


class AdminReportUserLeaveOverviewFilter(FilterSet):
    """User leave overview admin report filter."""

    user = django_filters.ModelChoiceFilter(
        field_name='leave__user',
        queryset=auth_models.User.objects.filter(is_active=True),
        widget=select2_widgets.Select2Widget,
    )
    from_date = django_filters.DateFilter(
        label='From',
        field_name='starts_at',
        lookup_expr='date__gte',
        widget=admin_widgets.AdminDateWidget(),
    )
    until_date = django_filters.DateFilter(
        label='Until',
        field_name='starts_at',
        lookup_expr='date__lte',
        widget=admin_widgets.AdminDateWidget(),
    )

    class Meta:
        model = models.LeaveDate
        fields = {}


class AdminReportUserWorkRatioByUserFilter(FilterSet):
    """User work ratio admin report filter."""
    user = django_filters.ModelChoiceFilter(
        queryset=auth_models.User.objects.filter(is_active=True),
        widget=select2_widgets.Select2Widget,
    )
    year = django_filters.MultipleChoiceFilter(
        choices=lambda: [[x, x] for x in (
            models.Timesheet.objects.values_list('year', flat=True).order_by('year').distinct())],
        widget=select2_widgets.Select2Widget,
    )

    class Meta:
        model = models.Timesheet
        fields = {}


class AdminReportUserWorkRatioByMonthFilter(FilterSet):
    """User work ratio admin report filter."""
    year = django_filters.ChoiceFilter(
        choices=lambda: [[x, x] for x in (
            models.Timesheet.objects.values_list('year', flat=True).order_by('year').distinct()
        )],
        initial='2019',
        widget=select2_widgets.Select2Widget,
    )
    month = django_filters.ChoiceFilter(
        choices=lambda: [[x + 1, x + 1] for x in range(12)],
        widget=select2_widgets.Select2Widget,
    )

    class Meta:
        model = models.Timesheet
        fields = {}


class AdminReportUserWorkRatioOverviewFilter(FilterSet):
    """User work ratio overview admin report filter."""
    user = django_filters.ModelChoiceFilter(
        queryset=auth_models.User.objects.filter(is_active=True),
        widget=select2_widgets.Select2Widget,
    )
    year = django_filters.ChoiceFilter(
        choices=lambda: [[x, x] for x in (
            models.Timesheet.objects.values_list('year', flat=True).order_by('year').distinct()
        )],
        widget=select2_widgets.Select2Widget,
    )

    class Meta:
        model = models.Timesheet
        fields = {}


class AdminReportResourceAvailabilityOverviewFilter(FilterSet):
    """User resource availability overview admin report filter."""
    user = (django_filters.ModelMultipleChoiceFilter(
        label='User',
        queryset=auth_models.User.objects.filter(is_active=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    group = (django_filters.ModelMultipleChoiceFilter(
        label='Group',
        queryset=auth_models.Group.objects.all(),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    contract = (django_filters.ModelMultipleChoiceFilter(
        label='Contract',
        queryset=models.Contract.objects.filter(active=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    from_date = django_filters.DateFilter(
        label='From',
        field_name='starts_at',
        lookup_expr='date__gte',
        widget=admin_widgets.AdminDateWidget(),
    )
    until_date = django_filters.DateFilter(
        label='Until',
        field_name='starts_at',
        lookup_expr='date__lte',
        widget=admin_widgets.AdminDateWidget(),
    )

    class Meta:
        model = auth_models.User
        fields = {}


class AdminReportInternalAvailabilityOverviewFilter(FilterSet):
    """Internal availability overview report filter."""
    user = (django_filters.ModelMultipleChoiceFilter(
        label='User',
        queryset=auth_models.User.objects.filter(is_active=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    group = (django_filters.ModelMultipleChoiceFilter(
        label='Group',
        queryset=auth_models.Group.objects.all(),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    contract = (django_filters.ModelMultipleChoiceFilter(
        label='Contract',
        queryset=models.Contract.objects.filter(active=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    date = django_filters.DateFilter(
        label='Date',
        field_name='starts_at',
        lookup_expr='date__gte',
        widget=admin_widgets.AdminDateWidget(),
    )

    class Meta:
        model = auth_models.User
        fields = {}


class AdminReportTimesheetMonthlyOverviewFilter(FilterSet):
    """Timesheet monthly overview admin report filter."""
    user = (django_filters.ModelMultipleChoiceFilter(
        label='User',
        queryset=auth_models.User.objects.filter(is_active=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    group = (django_filters.ModelMultipleChoiceFilter(
        label='Group',
        queryset=auth_models.Group.objects.all(),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    base_date = django_filters.DateFilter(
        label='Month',
        field_name='base_date',
        lookup_expr='date__gte',
        widget=admin_widgets.AdminDateWidget(),
    )

    class Meta:
        model = auth_models.User
        fields = {}


class AdminReportExpiringConsultancyContractOverviewFilter(FilterSet):
    """Expiring consultancy contract overview admin report filter."""
    company = (django_filters.ModelMultipleChoiceFilter(
        queryset=models.Company.objects.filter(internal=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    filter_internal = django_filters.ChoiceFilter(
        label='Filter internal contracts',
        empty_label="Show all project",
        choices=(
            ('show_noninternal', 'Show only non-internal consultancy contracts'),
            ('show_internal', 'Show only internal consultancy contracts'),
        )
    )

    class Meta:
        model = models.ConsultancyContract
        fields = {}


class AdminReportProjectContractOverviewFilter(FilterSet):
    """Project contract overview admin report filter."""
    contract_ptr = (django_filters.ModelMultipleChoiceFilter(
        label='Contract',
        field_name='contract_ptr',
        queryset=models.ProjectContract.objects.filter(active=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    customer = (django_filters.ModelMultipleChoiceFilter(
        queryset=models.Company.objects.filter(),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    company = (django_filters.ModelMultipleChoiceFilter(
        queryset=models.Company.objects.filter(internal=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    contractuser__user = (django_filters.ModelMultipleChoiceFilter(
        label='User',
        queryset=auth_models.User.objects.filter(is_active=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    contract_groups = (django_filters.ModelMultipleChoiceFilter(
        queryset=models.ContractGroup.objects.all(),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))

    class Meta:
        model = models.ProjectContract
        fields = {
            # TODO fix this!!!
            'contract_ptr': ['exact'],
            'name': ['icontains'],
            'contract_groups': ['exact'],
            'company': ['exact'],
            'customer': ['exact'],
            'contractuser__user': ['exact'],
        }


class AdminReportUserOvertimeOverviewFilter(FilterSet):
    """User overtime overview admin report filter."""
    user = django_filters.ModelChoiceFilter(
        field_name='leave__user',
        queryset=auth_models.User.objects.filter(is_active=True),
        widget=select2_widgets.Select2Widget,
    )
    from_date = django_filters.DateFilter(
        label='From',
        field_name='starts_at',
        lookup_expr='date__gte',
        widget=admin_widgets.AdminDateWidget(),
    )
    until_date = django_filters.DateFilter(
        label='Until',
        field_name='starts_at',
        lookup_expr='date__lte',
        widget=admin_widgets.AdminDateWidget(),
    )

    class Meta:
        model = models.LeaveDate
        fields = {}


class AdminReportExpiringSupportContractOverviewFilter(FilterSet):
    """Expiring support contract overview admin report filter."""
    company = (django_filters.ModelMultipleChoiceFilter(
        queryset=models.Company.objects.filter(internal=True),
        distinct=True,
        widget=select2_widgets.Select2MultipleWidget,
    ))
    filter_internal = django_filters.ChoiceFilter(
        label='Filter internal contracts',
        empty_label="Show all project",
        choices=(
            ('show_noninternal', 'Show only non-internal consultancy contracts'),
            ('show_internal', 'Show only internal consultancy contracts'),
        ),
    )

    class Meta:
        model = models.SupportContract
        fields = {}


class AdminReportInvoicedConsultancyContractOverviewFilter(FilterSet):

    from_date = django_filters.DateFilter(
        label='From',
        widget=admin_widgets.AdminDateWidget()
    )
    until_date = django_filters.DateFilter(
        label='Until',
        widget=admin_widgets.AdminDateWidget()
    )

    class Meta:
        model = models.ConsultancyContract
        fields = {
                'company',
        }


class AdminReportExpiringUserTrainingOverviewFilter(FilterSet):
    """Expiring support contract overview admin report filter."""
    ends_at_lte = django_filters.DateFilter(
        label='Ends before',
        field_name='ends_at',
        lookup_expr='lte',
        widget=admin_widgets.AdminDateWidget(),
    )

    class Meta:
        model = models.Training
        fields = {}
