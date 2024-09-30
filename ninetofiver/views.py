import copy
import logging
from collections import OrderedDict
from datetime import datetime, date, timedelta
from decimal import Decimal

from dateutil import parser
from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import models as auth_models, mixins as auth_mixins
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, F, Sum, Max, DecimalField
from django.forms.models import modelform_factory
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views import generic as generic_views
from django_tables2 import RequestConfig
from django_tables2.export.export import TableExport
from rest_framework import generics
from rest_framework import permissions
from wkhtmltopdf.views import PDFTemplateView
from dal import autocomplete

from ninetofiver import filters, settings
from ninetofiver import models
from ninetofiver import tables, calculation, pagination
from ninetofiver import redmine
from ninetofiver.models import ContractLog, Contract
from ninetofiver.utils import month_date_range, dates_in_range, hours_to_days
from .forms import LeaveDatePrefillForm

logger = logging.getLogger(__name__)


# Reused classes

class BaseTimesheetContractPdfExportServiceAPIView(PDFTemplateView, generics.GenericAPIView):
    """Export a timesheet contract to PDF."""

    filename = 'timesheet_contract.pdf'
    template_name = 'ninetofiver/timesheets/timesheet_contract_pdf_export.pug'

    def resolve_user_timesheet_contracts(self, context):
        """Resolve the users, timesheets and contracts for this export."""
        raise NotImplementedError()

    def render_to_response(self, context, **response_kwargs):
        items = self.resolve_user_timesheet_contracts(context)
        ctx = {
            'items': [],
        }

        for item in items:
            item_ctx = {
                'user': item[0],
                'timesheet': item[1],
                'contract': item[2],
            }

            item_ctx['activity_performances'] = (models.ActivityPerformance.objects
                                                 .filter(timesheet=item_ctx['timesheet'],
                                                         contract=item_ctx['contract'])
                                                 .order_by('date')
                                                 .select_related('performance_type')
                                                 .all())
            item_ctx['total_performed_hours'] = sum([x.duration for x in item_ctx['activity_performances']])
            item_ctx['total_performed_days'] = round(item_ctx['total_performed_hours'] / 8, 2)

            item_ctx['total_normalized_performed_hours'] = sum([x.normalized_duration for x in item_ctx['activity_performances']])
            item_ctx['total_normalized_performed_days'] = round(item_ctx['total_normalized_performed_hours'] / 8, 2)

            item_ctx['standby_performances'] = (models.StandbyPerformance.objects
                                                .filter(timesheet=item_ctx['timesheet'], contract=item_ctx['contract'])
                                                .order_by('date')
                                                .all())
            item_ctx['total_standby_days'] = round(len(item_ctx['standby_performances']), 2)

            # Create a performances dict, indexed by date
            performances = {}
            [performances.setdefault(str(x.date), {}).setdefault('activity', []).append(x)
                for x in item_ctx['activity_performances']]
            [performances.setdefault(str(x.date), {}).setdefault('standby', []).append(x)
                for x in item_ctx['standby_performances']]
            # Sort performances dict by date
            item_ctx['performances'] = OrderedDict()
            for day in sorted(performances):
                item_ctx['performances'][day] = performances[day]

            ctx['items'].append(item_ctx)

        return super().render_to_response(ctx, **response_kwargs)


# Homepage and others
def home_view(request):
    """Homepage."""
    context = {}
    return render(request, 'ninetofiver/home/index.pug', context)


@login_required
def account_view(request):
    """User-specific account page."""
    context = {}
    return render(request, 'ninetofiver/account/index.pug', context)


@login_required
def api_docs_view(request):
    """API docs view page."""
    context = {}
    return render(request, 'ninetofiver/api_docs/index.pug', context)


@login_required
def api_docs_redoc_view(request):
    """API docs redoc view page."""
    context = {}
    return render(request, 'ninetofiver/api_docs/redoc.pug', context)


@login_required
def api_docs_swagger_ui_view(request):
    """API docs swagger ui view page."""
    context = {}
    return render(request, 'ninetofiver/api_docs/swagger_ui.pug', context)


class ApiKeyCreateView(auth_mixins.LoginRequiredMixin, generic_views.CreateView):
    """View used to create an API key."""

    template_name = 'ninetofiver/api_keys/create.pug'
    success_url = reverse_lazy('api-key-list')

    def get_form_class(self):
        """Get the form class."""
        return modelform_factory(models.ApiKey, fields=('name', 'read_only',))

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class ApiKeyListView(auth_mixins.LoginRequiredMixin, generic_views.ListView):
    """List view for all API keys owned by the user."""

    context_object_name = 'tokens'
    template_name = 'ninetofiver/api_keys/list.pug'

    def get_queryset(self):
        return models.ApiKey.objects.filter(user=self.request.user)


class ApiKeyDeleteView(auth_mixins.LoginRequiredMixin, generic_views.DeleteView):
    """View used to delete an API key owned by the user."""

    context_object_name = "apikey"
    success_url = reverse_lazy('api-key-list')
    template_name = 'ninetofiver/api_keys/delete.pug'

    def get_queryset(self):
        return models.ApiKey.objects.filter(user=self.request.user)


class ContractAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Contract.objects.none()

        qs = Contract.objects.all()

        if self.q:
            qs = qs.filter(name__icontains=self.q)

        return qs

# Admin-only
@staff_member_required
def admin_leave_approve_view(request, leave_pk):
    """Approve the selected leaves."""
    leave_pks = list(map(int, leave_pk.split(',')))
    return_to_referer = request.GET.get('return', 'false').lower() == 'true'

    leaves = models.Leave.objects.filter(id__in=leave_pks, status=models.STATUS_PENDING)

    for leave in leaves:
        leave.status = models.STATUS_APPROVED
        leave.save()

    context = {
        'leaves': leaves,
    }

    if return_to_referer and request.META.get('HTTP_REFERER', None):
        return redirect(request.META.get('HTTP_REFERER'))

    return render(request, 'ninetofiver/admin/leaves/approve.pug', context)

@staff_member_required
def admin_leave_bulk_edit_dates(request, leave_pk):
    leave = models.Leave.objects.get(pk=leave_pk)
    if request.POST.get("do_action"):
        form = LeaveDatePrefillForm(data=request.POST, user=leave.user)
        if form.is_valid():
            leavedates = models.LeaveDate.objects.filter(leave=leave)
            return render(
                request,
                "admin/actions/action_bulkchange_leaves_confirm.html",
                {
                    "title": "Confirm the change",
                    "leavedates": leavedates,
                    "leave":leave,
                    "form": form,
                },
            )
    elif request.POST.get("confirm"):
        form = LeaveDatePrefillForm(data=request.POST, user=leave.user)
        if form.is_valid():
            #* delete all previous leavedates
            leavedates = models.LeaveDate.objects.filter(leave=leave)
            for leavedate in leavedates:
                leavedate.delete()
            start_date = form.cleaned_data["from_date"]
            end_date = form.cleaned_data["to_date"]
            # lent from api_v2/serializers.py
            leave_date_count = (end_date - start_date).days + 1
            employment_contract = None
            leave_dates = []
            #* Get leavedate ranges
            for i in range(leave_date_count):
                # Determine date for this day
                current_dt = datetime.combine(start_date, datetime.min.time()) + timedelta(days=i)
                current_date = current_dt.date()
                if ((not employment_contract) or (employment_contract.started_at > current_date) or
                        (employment_contract.ended_at and (employment_contract.ended_at < current_date))):
                    employment_contract = models.EmploymentContract.objects.filter(
                        Q(user=leave.user, started_at__lte=current_date) &
                        (Q(ended_at__isnull=True) | Q(ended_at__gte=current_date))
                    ).first()
                    work_schedule = employment_contract.work_schedule if employment_contract else None

                # Determine amount of hours to work on this day based on work schedule
                work_hours = 0.00
                if work_schedule:
                    work_hours = float(getattr(work_schedule, current_date.strftime('%A').lower(), Decimal(0.00)))

                # Determine existence of holidays on this day based on work schedule
                holiday = None
                if employment_contract:
                    holiday = models.Holiday.objects.filter(date=current_date,
                                                            country=employment_contract.company.country).first()

                # If we have to work a certain amount of hours on this day, and there is no holiday on that day,
                # add a leave date pair for that amount of hours
                if (work_hours > 0.0) and (not holiday):
                    # Ensure the leave starts when the working day does
                    pair_starts_at = current_dt.replace(hour=settings.DEFAULT_WORKING_DAY_STARTING_HOUR, minute=0,
                                                        second=1)
                    # Add work hours to pair start to obtain pair end
                    pair_ends_at = pair_starts_at.replace(hour=int(pair_starts_at.hour + work_hours),
                                                          minute=int((work_hours % 1) * 60), second=0)
                    # Log pair
                    leave_dates.append([pair_starts_at, pair_ends_at])
            if not leave_dates:
                messages.error(request, "No leave dates to change for this period")
            timesheet = None
            for pair in leave_dates:
                # Determine timesheet to use
                if (not timesheet) or ((timesheet.year != pair[0].year) or (timesheet.month != pair[0].month)):
                    timesheet = models.Timesheet.objects.get_or_create(user=leave.user, year=pair[0].year,
                                                                    month=pair[0].month)[0]

                models.LeaveDate.objects.create(leave=leave, timesheet=timesheet, starts_at=pair[0],
                                                ends_at=pair[1])
            messages.success(request, "Successfully changed LeaveDates")
            return redirect(reverse("admin:ninetofiver_leave_change", args=[leave_pk]))
    else:
        form = LeaveDatePrefillForm(user=leave.user)
    return render(
            request,
            "admin/actions/action_bulkchange_leavedate.html",
            {
                "title": "Change leave dates in bulk",
                "form": form,
                "leave":leave
            },
        )

@staff_member_required
def admin_leave_reject_view(request, leave_pk):
    """Reject the selected leaves."""
    leave_pks = list(map(int, leave_pk.split(',')))
    return_to_referer = request.GET.get('return', 'false').lower() == 'true'

    leaves = models.Leave.objects.filter(id__in=leave_pks, status=models.STATUS_PENDING)

    for leave in leaves:
        leave.status = models.STATUS_REJECTED
        leave.save()

    context = {
        'leaves': leaves,
    }

    if return_to_referer and request.META.get('HTTP_REFERER', None):
        return redirect(request.META.get('HTTP_REFERER'))

    return render(request, 'ninetofiver/admin/leaves/reject.pug', context)


@staff_member_required
def admin_timesheet_close_view(request, timesheet_pk):
    """Close the selected timesheets."""
    timesheet_pks = list(map(int, timesheet_pk.split(',')))
    return_to_referer = request.GET.get('return', 'false').lower() == 'true'

    timesheets = models.Timesheet.objects.filter(id__in=timesheet_pks, status=models.STATUS_PENDING)

    for timesheet in timesheets:
        timesheet.status = models.STATUS_CLOSED
        timesheet.save()

    context = {
        'timesheets': timesheets,
    }

    if return_to_referer and request.META.get('HTTP_REFERER', None):
        return redirect(request.META.get('HTTP_REFERER'))

    return render(request, 'ninetofiver/admin/timesheets/close.pug', context)


@staff_member_required
def admin_timesheet_activate_view(request, timesheet_pk):
    """Activate the selected timesheets."""
    timesheet_pks = list(map(int, timesheet_pk.split(',')))
    return_to_referer = request.GET.get('return', 'false').lower() == 'true'

    timesheets = models.Timesheet.objects.filter(id__in=timesheet_pks, status=models.STATUS_PENDING)

    for timesheet in timesheets:
        timesheet.status = models.STATUS_ACTIVE
        timesheet.save()

    context = {
        'timesheets': timesheets,
    }

    if return_to_referer and request.META.get('HTTP_REFERER', None):
        return redirect(request.META.get('HTTP_REFERER'))

    return render(request, 'ninetofiver/admin/timesheets/activate.pug', context)


@staff_member_required
def admin_report_index_view(request):
    """Report index."""

    user = request.user.id
    context = {
        'title': _('Reports'),
        'today': date.today(),
        'last_week': date.today() - relativedelta(weeks=1),
        'next_month': date.today() + relativedelta(months=1),
        'two_months_from_now': date.today() + relativedelta(months=2),
        'user': user,
    }

    return render(request, 'ninetofiver/admin/reports/index.pug', context)


@staff_member_required
def admin_report_timesheet_contract_overview_view(request):
    """Timesheet contract overview report."""
    fltr = filters.AdminReportTimesheetContractOverviewFilter(request.GET, models.Timesheet.objects)
    timesheets = fltr.qs.select_related('user')

    contracts = (models.Contract.objects.all())

    try:
        contract_ids = list(map(int, request.GET.getlist('performance__contract', [])))
    except Exception:
        contract_ids = None
    try:
        contract_types = list(map(str, request.GET.getlist('performance__contract__polymorphic_ctype__model', [])))
    except Exception:
        contract_types = None
    try:
        contract_companies = list(map(int, request.GET.getlist('performance__contract__company', [])))
    except Exception:
        contract_companies = None
    try:
        contract_customers = list(map(int, request.GET.getlist('performance__contract__customer', [])))
    except Exception:
        contract_customers = None
    try:
        contract_groups = list(map(int, request.GET.getlist('performance__contract__contract_groups', [])))
    except Exception:
        contract_groups = None

    if contract_ids:
        contracts = contracts.filter(id__in=contract_ids)
    if contract_types:
        contracts = contracts.filter(polymorphic_ctype__model__in=contract_types)
    if contract_companies:
        contracts = contracts.filter(company__id__in=contract_companies)
    if contract_customers:
        contracts = contracts.filter(customer__id__in=contract_customers)
    if contract_groups:
        contracts = contracts.filter(contract_groups__id__in=contract_groups)

    contracts = contracts.values_list('id', flat=True)

    data = []
    for timesheet in timesheets:
        date_range = timesheet.get_date_range()
        range_info = calculation.get_range_info([timesheet.user], date_range[0], date_range[1], summary=True)

        for contract_performance in range_info[timesheet.user.id]['summary']['performances']:
            if (not contracts) or (contract_performance['contract'].id in contracts):
                data.append({
                    'contract': contract_performance['contract'],
                    'duration': contract_performance['duration'],
                    'standby_days': contract_performance['standby_days'],
                    'timesheet': timesheet,
                })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.TimesheetContractOverviewTable(data)
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('Timesheet contract overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/timesheet_contract_overview.pug', context)

@staff_member_required
def admin_report_contract_logs_overview_view(request):
    """Contract logs overview report."""
    fltr = filters.AdminReportContractLogsOverviewFilter(
        request.GET, models.ContractLog.objects
    )
    contract = (
        get_object_or_404(models.Contract.objects, pk=request.GET.get("contract", None))
        if request.GET.get("contract")
        else None
    )
    logtypes = (
        get_object_or_404(
            models.ContractLogType.objects, pk=request.GET.get("logtypes", None)
        )
        if request.GET.get("logtypes")
        else None
    )
    data = []
    if contract:
        logs = fltr.qs.filter(contract=contract)
        if logtypes:
            logs = logs.filter(logtype=logtypes)
        for log in logs:
            data.append(
                {
                    "log": log.description,
                    "contract": contract,
                    "log_type": log.contract_log_type,
                    "date": log.date,
                }
            )
    config = RequestConfig(
        request,
        paginate={"per_page": pagination.CustomizablePageNumberPagination.page_size},
    )
    table = tables.ContractLogOverviewTable(data)
    config.configure(table)

    export_format = request.GET.get("_export", None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response("table.{}".format(export_format))

    context = {
        "title": _("Contract logs overview"),
        "table": table,
        "filter": fltr,
    }

    return render(
        request, "ninetofiver/admin/reports/timesheet_contract_overview.pug", context
    )

@staff_member_required
def admin_report_timesheet_overview_view(request):
    """Timesheet overview report."""
    fltr = filters.AdminReportTimesheetOverviewFilter(request.GET, models.Timesheet.objects)
    timesheets = fltr.qs.select_related('user')
    company = fltr.data.get('user__employmentcontract__company', None)
    year = int(fltr.data['year']) if fltr.data.get('year', None) else None
    month = int(fltr.data['month']) if fltr.data.get('month', None) else None

    # If we're filtering on company and period (year or year + month), ensure we're only showing timesheets
    # for users who worked at the company for the period we're filtering on
    if company and year:
        period_start, period_end = month_date_range(year, month) if month else (date(year, 1, 1), date(year, 12, 31))
        timesheets = timesheets.filter(Q(user__employmentcontract__ended_at__isnull=True,
                                         user__employmentcontract__started_at__lte=period_end,
                                         user__employmentcontract__company__id=company) |
                                       Q(user__employmentcontract__ended_at__isnull=False,
                                         user__employmentcontract__ended_at__gte=period_start,
                                         user__employmentcontract__started_at__lte=period_end,
                                         user__employmentcontract__company__id=company))

    data = []
    for timesheet in timesheets:
        date_range = timesheet.get_date_range()
        range_info = calculation.get_range_info([timesheet.user], date_range[0], date_range[1])
        range_info = range_info[timesheet.user.id]
        range_info_to_day = calculation.get_range_info([timesheet.user], date_range[0], datetime.now().date())
        range_info_to_day = range_info_to_day[timesheet.user.id]

        data.append({
            'timesheet': timesheet,
            'range_info': range_info,
            'range_info_to_day': range_info_to_day,
        })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size * 4})
    table = tables.TimesheetOverviewTable(data)
    config.configure(table)


    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('Timesheet overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/timesheet_overview.pug', context)


@staff_member_required
def admin_report_user_range_info_view(request):
    """User range info report."""
    fltr = filters.AdminReportUserRangeInfoFilter(request.GET, models.Timesheet.objects.all())
    user = get_object_or_404(auth_models.User.objects,
                             pk=request.GET.get('user', None), is_active=True) if request.GET.get('user') else None
    from_date = parser.parse(request.GET.get('from_date', None)).date() if request.GET.get('from_date') else None
    until_date = parser.parse(request.GET.get('until_date', None)).date() if request.GET.get('until_date') else None

    data = []

    if user and from_date and until_date and (until_date >= from_date):
        range_info = calculation.get_range_info([user], from_date, until_date, daily=True)[user.id]

        for day in sorted(range_info['details'].keys()):
            day_detail = range_info['details'][day]
            data.append({
                'day_detail': day_detail,
                'date': parser.parse(day),
                'user': user,
            })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size * 2})
    table = tables.UserRangeInfoTable(data)
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('User range info'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/user_range_info.pug', context)



@staff_member_required
def admin_report_user_leave_group_overview_view(request):
    """User leave overview report for group/company."""
    fltr = filters.AdminReportUserGroupLeaveOverviewFilter(request.GET, models.LeaveDate.objects
                                                      .filter(leave__status=models.STATUS_APPROVED))
    group = get_object_or_404(auth_models.Group.objects,
                             pk=request.GET.get('group', None)) if request.GET.get('group') else None
    company = get_object_or_404(models.Company.objects,
                             pk=request.GET.get('company', None)) if request.GET.get('company') else None
    from_date = parser.parse(request.GET.get('from_date', None)).date() if request.GET.get('from_date') else None
    until_date = parser.parse(request.GET.get('until_date', None)).date() if request.GET.get('until_date') else None
    data = []

    if from_date and until_date and (until_date >= from_date):
        leave_types = models.LeaveType.objects.all()

        # Grab leave dates, sort them in a dict per user, then by leave type while summing them
        leave_dates = models.LeaveDate.objects.filter(leave__status=models.STATUS_APPROVED,starts_at__gte=from_date,ends_at__lte=until_date.replace(day=until_date.day+1))
        leave_date_data = {}
        for leave_date in leave_dates: # for each leavedate:
            user = leave_date.leave.user
            user_id = user.id
            if(group and not leave_date.leave.user.groups.filter(name=group.name).exists()): # if group is defined and user is not in it, skip
                logger.debug(f"Skipping entry for user {user.id}, because it is not in group {group.id}")
                continue
            if(company): # if company is defined
                ec = models.EmploymentContract.objects.filter(user=user,company=company) # get all employment contracts which contain the user and the company
                if(not ec.exists()): # if no contract is found, skip
                    logger.debug(f"User {user.id} has no contract with company {company.id}")
                    continue
                skip_user = False
                for contract in ec:
                    logger.debug(contract.started_at >= from_date)
                    skip_user = contract.started_at > until_date or contract.ended_at <= from_date # should handle situations where user is looking up a period where user should be under another company (expired contracts)
                if skip_user:
                    logger.debug(f"Skipping entry for user {user.id} because of no valid contract in specified period with selected company {company.id}")
                    continue

            if(not user_id in leave_date_data):
                leave_date_data.setdefault(user_id,{"leave_type_hours":{}, "user":leave_date.leave.user,"from_date":from_date,"until_date":until_date})
            for leave_type in leave_types: # create entry for every leave type
                if(not leave_type.name in leave_date_data[user_id]["leave_type_hours"]):
                    leave_date_data[user_id]["leave_type_hours"].setdefault(leave_type.name,0)
            leave_date_data[user_id]["leave_type_hours"][leave_date.leave.leave_type.name] += sum([Decimal(round((leave_date.ends_at - leave_date.starts_at).total_seconds() / 3600, 2))])
        for u in leave_date_data.keys():
            data.append(leave_date_data[u])
        logger.debug(len(leave_date_data.keys()))

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.UserGroupLeaveOverviewTable(data)
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('User leave overview by group/company'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/user_leave_overview.pug', context)


@staff_member_required
def admin_report_user_leave_overview_view(request):
    """User leave overview report."""
    fltr = filters.AdminReportUserLeaveOverviewFilter(request.GET, models.LeaveDate.objects
                                                      .filter(leave__status=models.STATUS_APPROVED))
    user = get_object_or_404(auth_models.User.objects,
                             pk=request.GET.get('user', None), is_active=True) if request.GET.get('user') else None
    from_date = parser.parse(request.GET.get('from_date', None)).date() if request.GET.get('from_date') else None
    until_date = parser.parse(request.GET.get('until_date', None)).date() if request.GET.get('until_date') else None
    data = []

    if user and from_date and until_date and (until_date >= from_date):
        # Grab timesheets, index them by year, month
        timesheets = (models.Timesheet.objects
                      .filter(user=user)
                      .filter(
                          Q(year=from_date.year, month__gte=from_date.year) |
                          Q(year__gt=from_date.year, year__lt=until_date.year) |
                          Q(year=until_date.year, month__lte=until_date.month)))
        timesheet_data = {}
        for timesheet in timesheets:
            timesheet_data.setdefault(timesheet.year, {})[timesheet.month] = timesheet

        # Grab leave types, index them by ID
        leave_types = models.LeaveType.objects.all()

        # Grab leave dates, index them by year, then month, then leave type ID
        leave_dates = fltr.qs.filter().select_related('leave', 'leave__leave_type')
        leave_date_data = {}
        for leave_date in leave_dates:
            (leave_date_data
                .setdefault(leave_date.starts_at.year, {})
                .setdefault(leave_date.starts_at.month, {})
                .setdefault(leave_date.leave.leave_type.id, [])
                .append(leave_date))

        # Iterate over years, months to create monthly data
        current_date = copy.deepcopy(from_date)
        while current_date.strftime('%Y%m') <= until_date.strftime('%Y%m'):
            month_leave_dates = leave_date_data.get(current_date.year, {}).get(current_date.month, {})
            month_leave_type_hours = {}

            # Iterate over leave types to gather totals
            for leave_type in leave_types:
                duration = sum([Decimal(str(round((x.ends_at - x.starts_at).total_seconds() / 3600, 2)))
                                for x in month_leave_dates.get(leave_type.id, [])])
                month_leave_type_hours[leave_type.name] = duration

            data.append({
                'year': current_date.year,
                'month': current_date.month,
                'user': user,
                'timesheet': timesheet_data.get(current_date.year, {}).get(current_date.month, None),
                'leave_type_hours': month_leave_type_hours,
            })

            current_date += relativedelta(months=1)

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.UserLeaveOverviewTable(data)
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('User leave overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/user_leave_overview.pug', context)


@staff_member_required
def admin_report_user_work_ratio_by_user_view(request):
    """Shows the work ratio (billable vs. non-billable vs. leave) of a specific user."""
    fltr = filters.AdminReportUserWorkRatioByUserFilter(request.GET, models.Timesheet.objects)
    data = []

    if fltr.data.get('user', None) and fltr.data.get('year', None):
        year = int(fltr.data['year'])
        user = get_object_or_404(auth_models.User.objects,
                                 pk=request.GET.get('user', None), is_active=True) if request.GET.get('user') else None

        timesheets = fltr.qs.select_related('user').order_by('year', 'month')

        for timesheet in timesheets:
            date_range = timesheet.get_date_range()
            range_info = calculation.get_range_info([timesheet.user], date_range[0], date_range[1], summary=True)
            range_info = range_info[timesheet.user.id]

            data.append({
                'year': timesheet.year,
                'month': timesheet.month,
                'work_hours': range_info['work_hours'],
                'customer_hours': sum([x['duration'] for x in range_info['summary']['performances']
                                 if x['contract'].customer != x['contract'].company]),
                'internal_hours': sum([x['duration'] for x in range_info['summary']['performances']
                                      if x['contract'].customer == x['contract'].company]),
                'leaves': range_info['leave_hours'],
            })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.UserWorkRatioByUserTable(data)
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('User work ratio By User'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/user_work_ratio_by_user.pug', context)

@staff_member_required
def admin_report_user_work_ratio_by_month_view(request):
    """Shows the work ratio (billable vs. non-billable vs. leave) of a specific month."""
    fltr = filters.AdminReportUserWorkRatioByMonthFilter(request.GET, models.Timesheet.objects)
    data = []

    from pprint import pprint

    if fltr.data.get('month', None) and fltr.data.get('year', None):

        for timesheet in fltr.qs.select_related('user'):
            date_range = timesheet.get_date_range()
            range_info = calculation.get_range_info([timesheet.user], date_range[0], date_range[1], summary=True)
            range_info = range_info[timesheet.user.id]

            data.append({
                'user':           timesheet.user,
                'work_hours':     range_info['work_hours'],
                'customer_hours': sum([x['duration'] for x in range_info['summary']['performances'] if x['contract'].customer != x['contract'].company]),
                'internal_hours': sum([x['duration'] for x in range_info['summary']['performances'] if x['contract'].customer == x['contract'].company]),
                'leaves':         range_info['leave_hours'],
                })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.UserWorkRatioByMonthTable(data, order_by='user')
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('User work ratio By Month'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/user_work_ratio_by_month.pug', context)

@staff_member_required
def admin_report_user_work_ratio_overview_view(request):
    """User work ratio overview report."""
    fltr = filters.AdminReportUserWorkRatioOverviewFilter(request.GET, models.Timesheet.objects)
    data = []

    if fltr.data.get('user', None) and fltr.data.get('year', None):
        year = int(fltr.data['year'])
        user = get_object_or_404(auth_models.User.objects,
                                 pk=request.GET.get('user', None), is_active=True) if request.GET.get('user') else None

        timesheets = fltr.qs.select_related('user').order_by('year', 'month')

        for timesheet in timesheets:
            date_range = timesheet.get_date_range()
            range_info = calculation.get_range_info([timesheet.user], date_range[0], date_range[1], summary=True)
            range_info = range_info[timesheet.user.id]

            total_hours = range_info['performed_hours'] + range_info['leave_hours']
            leave_hours = range_info['leave_hours']
            consultancy_hours = sum([x['duration'] for x in range_info['summary']['performances']
                                    if x['contract'].get_real_instance_class() == models.ConsultancyContract])
            project_hours = sum([x['duration'] for x in range_info['summary']['performances']
                                if x['contract'].get_real_instance_class() == models.ProjectContract])
            support_hours = sum([x['duration'] for x in range_info['summary']['performances']
                                if x['contract'].get_real_instance_class() == models.SupportContract])

            consultancy_pct = round((consultancy_hours / (total_hours if total_hours else 1.0)) * 100, 2)
            project_pct = round((project_hours / (total_hours if total_hours else 1.0)) * 100, 2)
            support_pct = round((support_hours / (total_hours if total_hours else 1.0)) * 100, 2)
            leave_pct = round((leave_hours / (total_hours if total_hours else 1.0)) * 100, 2)

            data.append({
                'year': timesheet.year,
                'month': timesheet.month,
                'user': timesheet.user,
                'total_hours': total_hours,
                'leave_hours': leave_hours,
                'consultancy_hours': consultancy_hours,
                'project_hours': project_hours,
                'support_hours': support_hours,
                'leave_pct': leave_pct,
                'consultancy_pct': consultancy_pct,
                'project_pct': project_pct,
                'support_pct': support_pct,
            })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.UserWorkRatioOverviewTable(data)
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('User work ratio overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/user_work_ratio_overview.pug', context)


class AvailabilityView(View):
    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(AvailabilityView, self).dispatch(*args, **kwargs)

    def get_active_users(self):
        return auth_models.User.objects.filter(is_active=True).distinct()

    def fetch_contract_user_work_schedules(self, users, from_date, until_date):
        contract_user_work_schedules = (models.ContractUserWorkSchedule.objects
                .filter(contract_user__user__in=users)
                .filter(Q(ends_at__isnull=True, starts_at__lte=until_date) |
                        Q(ends_at__isnull=False, starts_at__lte=until_date,
                          ends_at__gte=from_date))
                .select_related('contract_user', 'contract_user__user',
                                'contract_user__contract_role', 'contract_user__contract',
                                'contract_user__contract__customer'))

        # Index contract user work schedules by user
        contract_user_work_schedule_data = {}
        for contract_user_work_schedule in contract_user_work_schedules:
            (contract_user_work_schedule_data
             .setdefault(contract_user_work_schedule.contract_user.user.id, [])
             .append(contract_user_work_schedule))

        return contract_user_work_schedule_data

    def fetch_employment_contracts(self, from_date, until_date, users):

        employment_contracts = (models.EmploymentContract.objects
                                .filter(
            (Q(ended_at__isnull=True) & Q(started_at__lte=until_date)) |
            (Q(started_at__lte=until_date) & Q(ended_at__gte=from_date)),
            user__in=users)
                                .order_by('started_at')
                                .select_related('user', 'company', 'work_schedule'))
        # Index employment contracts by user ID
        employment_contract_data = {}
        for employment_contract in employment_contracts:
            (employment_contract_data
             .setdefault(employment_contract.user.id, [])
             .append(employment_contract))
        return employment_contract_data


class ResourceAvailabilityOverviewView(AvailabilityView):
    """Resource availability overview report."""
    def get(self, request):
        data = []
        fltr = filters.AdminReportResourceAvailabilityOverviewFilter(request.GET, models.Timesheet.objects)
        from_date = parser.parse(request.GET.get('from_date', None)).date() if request.GET.get('from_date') else None
        until_date = parser.parse(request.GET.get('until_date', None)).date() if request.GET.get('until_date') else None

        users = self.get_active_users()
        try:
            user_ids = list(map(int, request.GET.getlist('user', [])))
            users = users.filter(id__in=user_ids) if user_ids else users
        except Exception:
            pass
        try:
            group_ids = list(map(int, request.GET.getlist('group', [])))
            users = users.filter(groups__in=group_ids) if group_ids else users
        except Exception:
            pass

        try:
            contract_ids = list(map(int, request.GET.getlist('contract', [])))
            users = users.filter(contractuser__contract__in=contract_ids) if contract_ids else users
        except Exception:
            pass

        if users and from_date and until_date and (until_date >= from_date):
            dates = dates_in_range(from_date, until_date)

            # Fetch contract user work schedules
            contract_user_work_schedule_data = self.fetch_contract_user_work_schedules(users, from_date, until_date)

            # Fetch employment contracts
            employment_contract_data = self.fetch_employment_contracts(from_date, until_date, users)

            # Fetch availability
            availability = calculation.get_availability_info(users, from_date, until_date)

            # Iterate over users, days to create daily user data
            for user in users:
                user_data = {
                    'user': user,
                    'days': {},
                }
                data.append(user_data)

                for current_date in dates:
                    date_str = str(current_date)
                    user_day_data = user_data['days'][date_str] = {}

                    day_availability = availability[str(user.id)][date_str].day_tags
                    day_contract_user_work_schedules = []
                    day_scheduled_hours = Decimal('0.00')
                    day_work_hours = Decimal('0.00')

                    # Get contract user work schedules for this day
                    # This allows us to determine the scheduled hours for this user
                    for contract_user_work_schedule in contract_user_work_schedule_data.get(user.id, []):
                        if (contract_user_work_schedule.starts_at <= current_date) and \
                                ((not contract_user_work_schedule.ends_at) or
                                 (contract_user_work_schedule.ends_at >= current_date)):
                            day_contract_user_work_schedules.append(contract_user_work_schedule)
                            day_scheduled_hours += getattr(contract_user_work_schedule,
                                                           current_date.strftime('%A').lower(), Decimal('0.00'))

                    # Get employment contract for this day
                    # This allows us to determine the required hours for this user
                    employment_contract = None
                    try:
                        for ec in employment_contract_data[user.id]:
                            if (ec.started_at <= current_date) and ((not ec.ended_at) or (ec.ended_at >= current_date)):
                                employment_contract = ec
                                break
                    except KeyError:
                        pass

                    work_schedule = employment_contract.work_schedule if employment_contract else None
                    if work_schedule:
                        day_work_hours = getattr(work_schedule, current_date.strftime('%A').lower(), Decimal('0.00'))

                    user_day_data['availability'] = day_availability
                    user_day_data['contract_user_work_schedules'] = day_contract_user_work_schedules
                    user_day_data['scheduled_hours'] = day_scheduled_hours
                    user_day_data['work_hours'] = day_work_hours
                    user_day_data['enough_hours'] = day_scheduled_hours >= day_work_hours

        config = RequestConfig(request,
                               paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size * 4})
        table = tables.ResourceAvailabilityOverviewTable(from_date, until_date, data)
        config.configure(table)

        export_format = request.GET.get('_export', None)
        if TableExport.is_valid_format(export_format):
            exporter = TableExport(export_format, table)
            return exporter.response('table.{}'.format(export_format))

        context = {
            'title': _('Resource availability overview'),
            'table': table,
            'filter': fltr,
        }

        return render(request, 'ninetofiver/admin/reports/resource_availability_overview.pug', context)


class TimesheetMonthlyOverviewView(AvailabilityView):
    """Timesheet monthly overview report."""

    def get(self, request):
        data = []
        fltr = filters.AdminReportTimesheetMonthlyOverviewFilter(request.GET, models.Timesheet.objects)
        # TODO: Maybe replace the date selection with a dropdown with months?
        base_date = parser.parse(request.GET.get('base_date', None)).date() if request.GET.get('base_date') else datetime.today()

        # The default month should not be the current one, but previous
        fetch_previous = request.GET.get('fetch_previous', None)
        if fetch_previous:
            base_date = base_date - relativedelta(months=1)
        from_date = base_date.replace(day=1)
        until_date = from_date + relativedelta(months=1) - relativedelta(days=1)

        users = self.get_active_users()
        try:
            user_ids = list(map(int, request.GET.getlist('user', [])))
            users = users.filter(id__in=user_ids) if user_ids else users
        except Exception:
            pass
        try:
            group_ids = list(map(int, request.GET.getlist('group', [])))
            users = users.filter(groups__in=group_ids) if group_ids else users
        except Exception:
            pass

        try:
            contract_ids = list(map(int, request.GET.getlist('contract', [])))
            users = users.filter(contractuser__contract__in=contract_ids) if contract_ids else users
        except Exception:
            pass

        if users and from_date and until_date and (until_date >= from_date):
            dates = dates_in_range(from_date, until_date)

            # Fetch availability
            availability = calculation.get_availability_info(users, from_date, until_date)

            # Fetch contract user work schedules
            contract_user_work_schedule_data = self.fetch_contract_user_work_schedules(users, from_date, until_date)

            # Fetch employment contracts
            employment_contract_data = self.fetch_employment_contracts(from_date, until_date, users)

            # Iterate over users, days to create daily user data
            for user in users:
                user_data = {
                    'user': user,
                    'days': {},
                }

                for current_date in dates:
                    day_contract_user_work_schedules = []
                    day_scheduled_hours = Decimal('0.00')

                    # Get contract user work schedules for this day
                    # This allows us to determine the scheduled hours for this user
                    for contract_user_work_schedule in contract_user_work_schedule_data.get(user.id, []):
                        if (contract_user_work_schedule.starts_at <= current_date) and \
                                ((not contract_user_work_schedule.ends_at) or
                                 (contract_user_work_schedule.ends_at >= current_date)):
                            day_contract_user_work_schedules.append(contract_user_work_schedule)
                            day_scheduled_hours += getattr(contract_user_work_schedule,
                                                           current_date.strftime('%A').lower(), Decimal('0.00'))

                    user_day_data = {}

                    date_str = str(current_date)
                    day_availability = availability[str(user.id)][date_str]
                    day_availability_tags = day_availability.day_tags
                    user_day_data['availability'] = day_availability_tags
                    user_day_data['leave_dates'] = day_availability.leave_dates

                    user_day_data['contract_user_work_schedules'] = day_contract_user_work_schedules
                    user_day_data['scheduled_hours'] = day_scheduled_hours

                    # Get employment contract for this day
                    # This allows us to determine the required hours for this user
                    employment_contract = None
                    try:
                        for ec in employment_contract_data[user.id]:
                            if (ec.started_at <= current_date) and ((not ec.ended_at) or (ec.ended_at >= current_date)):
                                employment_contract = ec
                                break
                    except KeyError:
                        pass

                    work_schedule = employment_contract.work_schedule if employment_contract else None
                    day_work_hours = Decimal('0.00')
                    if work_schedule:
                        day_work_hours = getattr(work_schedule, current_date.strftime('%A').lower(), Decimal('0.00'))
                    user_day_data['work_hours'] = day_work_hours
                    user_day_data['enough_hours'] = day_scheduled_hours >= day_work_hours

                    user_data['days'][date_str] = user_day_data

                data.append(user_data)

        config = RequestConfig(request,
                               paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size * 4})
        table = tables.TimesheetMonthlyOverviewTable(from_date, until_date, data)
        config.configure(table)


        export_format = request.GET.get('_export', None)
        if TableExport.is_valid_format(export_format):
            exporter = TableExport(export_format, table)
            return exporter.response('table.{}'.format(export_format))

        context = {
            'title': _('Timesheet monthly overview'),
            'table': table,
            'filter': fltr,
        }

        return render(request, 'ninetofiver/admin/reports/timesheet_monthly_overview.pug', context)


@staff_member_required
def admin_report_expiring_consultancy_contract_overview_view(request):
    """Expiring consultancy User work ratio overview report."""
    fltr = filters.AdminReportExpiringConsultancyContractOverviewFilter(request.GET,
                                                                        models.ConsultancyContract.objects)
    company = request.GET.getlist('company', [])
    filter_internal = request.GET.get('filter_internal')
    data = []

    contracts = (
        models.ConsultancyContract.objects.all()
        .select_related('customer')
        .prefetch_related('contractuser_set', 'contractuser_set__contract_role', 'contractuser_set__user')
        .filter(active=True)
    )

    if company:
        contracts = contracts.filter(company__in=company)

    if filter_internal == "show_noninternal":
        contracts = contracts.exclude(customer=F('company'))
    elif filter_internal == "show_internal":
        contracts = contracts.filter(customer=F('company'))
    elif filter_internal == "show_all" or filter_internal == "":
        # Do nothing - show all. (#readability_counts)
        pass

    for contract in contracts:
        alotted_hours = contract.duration
        performed_hours = (models.ActivityPerformance.objects
                           .filter(contract=contract)
                           .aggregate(performed_hours=Sum(F('duration') * F('performance_type__multiplier'))))['performed_hours']
        performed_hours = performed_hours if performed_hours else Decimal('0.00')
        remaining_hours = (alotted_hours - performed_hours) if alotted_hours else None

        calculated_enddate = contract.ends_at
        if remaining_hours is not None:
            business_days_to_add = hours_to_days(remaining_hours)
            current_date = date.today().replace(day=1)
            while business_days_to_add > 0:
                current_date += timedelta(days=1)
                weekday = current_date.weekday()
                if weekday >= 5: # sunday = 6
                    continue
                business_days_to_add -= 1
            calculated_enddate = current_date

            if contract.ends_at is not None and contract.ends_at < calculated_enddate:
                calculated_enddate = contract.ends_at

        try:
            contract_log = ContractLog.objects.filter(contract=contract).latest('date').contract_log_type
        except ObjectDoesNotExist:
            contract_log = None

        data.append({
            'contract': contract,
            'contract_log': contract_log,
            'users': [contract_user.user for contract_user in contract.contractuser_set.all().order_by('user__first_name', 'user__last_name', 'user__username')],
            'alotted_hours': alotted_hours,
            'performed_hours': performed_hours,
            'remaining_hours': remaining_hours,
            'calculated_enddate': calculated_enddate if calculated_enddate is not None else date(2999, 12, 31)
        })

    config = RequestConfig(request, paginate=False)
    table = tables.ExpiringConsultancyContractOverviewTable(data, order_by='calculated_enddate')
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('Expiring consultancy contract overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/expiring_consultancy_contract_overview.pug', context)


@staff_member_required
def admin_report_invoiced_consultancy_contract_overview_view(request):

    # Copy QueryDict of GET - so we can inject from_date and until_date if not filled
    request_get = request.GET.copy()

    # Update from and until date so they are not missing and are the first and last day of the selected month(s)
    try:
        from_date = datetime.strptime(request.GET.get('from_date'), '%Y-%m-%d').date().replace(day=1)
    except Exception:
        from_date = datetime.today().replace(day=1).date()
    request_get['from_date'] = from_date.strftime("%Y-%m-%d")

    try:
        until_date = (datetime.strptime(request.GET.get('until_date'), '%Y-%m-%d').date().replace(day=1) + relativedelta(months=1) - relativedelta(days=1))
    except Exception:
        until_date = (datetime.today().replace(day=1) + relativedelta(months=1) - relativedelta(days=1)).date()
    request_get['until_date'] = until_date.strftime("%Y-%m-%d")

    # invoice_date is last day of the month of the specific period selected in the report
    #  - if that date is less than 15 days before or after the current date
    # else the current date.
    invoice_date = until_date
    if date.today() - timedelta(days=-15) < invoice_date < date.today() - timedelta(days=15):
        invoice_date = date.today()


    fltr = filters.AdminReportInvoicedConsultancyContractOverviewFilter(request_get,
                                                                        models.ConsultancyContract.objects)
    data = []


    performances = models.ActivityPerformance.objects
    performances = performances.filter(
            Q(timesheet__month__gte=from_date.month) & Q(timesheet__year__gte=from_date.year) &
            Q(timesheet__month__lte=until_date.month) & Q(timesheet__year__lte=until_date.year)
            )
    performances = performances.filter(Q(contract__polymorphic_ctype__model='consultancycontract'))

    try:
        company = list(map(int, request.GET.getlist('company', [])))
    except Exception:
        company = None
    if company:
        performances = performances.filter(
            Q(contract__company__id__in=company)
        )

    # Prefetching some more info in 1 DB query
    performances = performances.select_related('performance_type')
    performances = performances.select_related('contract__consultancycontract')
    performances = performances.select_related('timesheet')
    performances = performances.select_related('timesheet__user')

    # We can't access ConsultancyContract specific items, like day_rate, when using the select_related on the performances
    # Therefore we fetch all ConsultancyContracts and we match them in code
    consultancycontracts = models.ConsultancyContract.objects
    consultancycontracts = consultancycontracts.filter(contract_ptr_id__in=performances.values_list('contract_id', flat=True).distinct())
    consultancycontracts = consultancycontracts.select_related('company')
    consultancycontracts = consultancycontracts.select_related('customer')

    invoiceitems = models.InvoiceItem.objects
    invoiceitems = invoiceitems.filter(invoice__period_starts_at__lte=until_date, invoice__period_ends_at__gte=from_date)
    invoiceitems = invoiceitems.select_related('invoice')


    performed_hours = []

    for performance in performances:

        contract_already_added = False
        for performed_hour in performed_hours:
            if performed_hour['contract'].id == performance.contract.id:
                performed_hour['duration'] = performed_hour['duration'] + ( performance.duration * performance.performance_type.multiplier )
                performed_hour['users'].add(performance.timesheet.user)
                contract_already_added = True

        if not contract_already_added:
            # We loop through all ConsultancyContracts and find the matching one
            # We will use the seperate contract instead the prefetched contract though performances
            for contract in consultancycontracts:
                if performance.contract.id == contract.id:
                    performed_hours.append({
                        'contract': contract,
                        'duration': performance.duration * performance.performance_type.multiplier,
                        'users':    set([performance.timesheet.user])
                        })


    for performed_hour in performed_hours:

        invoiced_total_amount = 0
        invoiced_missing = False
        for invoiceitem in invoiceitems:
            if invoiceitem.invoice.contract_id == performed_hour['contract'].id:
                invoiced_total_amount += invoiceitem.price * invoiceitem.amount
                if from_date > invoiceitem.invoice.period_starts_at or until_date < invoiceitem.invoice.period_ends_at:
                    invoiced_missing = True

        data.append({
            'contract': performed_hour['contract'],
            'users': performed_hour['users'],
            'performed_hours': performed_hour['duration'],
            'day_rate': performed_hour['contract'].day_rate,
            'to_be_invoiced': round(performed_hour['duration'] * performed_hour['contract'].day_rate / 8, 2),
            'invoiced': round(invoiced_total_amount, 2),
            'invoiced_missing': invoiced_missing,
            'action': {
                'period_starts_at': from_date,
                'period_ends_at': until_date,
                'date': invoice_date,
                'price': performed_hour['contract'].day_rate,
                'amount': hours_to_days(performed_hour['duration'], rounded=False),
            },
        })


    config = RequestConfig(request, paginate=False)
    table = tables.InvoicedConsultancyContractOverviewTable(data, order_by='-to_be_invoiced,-performed_hours')
    config.configure(table)

    context = {
        'title':  _('Invoiced consultancy contract overview'),
        'table':  table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/invoiced_consultancy_contract_overview.pug', context)


@staff_member_required
def admin_report_project_contract_overview_view(request):
    """Project contract overview report."""
    fltr = filters.AdminReportProjectContractOverviewFilter(request.GET, models.ProjectContract.objects)
    data = []

    if True in map(bool, list(fltr.data.values())):
        contracts = (fltr.qs.all()
                    .select_related('customer')
                    .prefetch_related('contractestimate_set', 'contractestimate_set__contract_role','attachments')
                    .filter(active=True))

        for contract in contracts:
            # Keep track of totals
            performed_hours = Decimal('0.00')
            estimated_hours = Decimal('0.00')

            # List containing estimated and performed hours per role
            contract_role_data = {}
            # List containing performed hours per country
            country_data = {}
            # List containing performed hours per user
            user_data = {}
            # List containing performed hours per month
            month_data = {}
            # List containing contract attachments
            attachment_data = {}

            # Fetch each performance for the contract, annotated with country
            performances = (models.ActivityPerformance.objects
                            .select_related('performance_type', 'contract_role', 'timesheet__user', 'timesheet__user__userinfo')
                            .filter(contract=contract))

            # Iterate over estimates to populate contract role data
            for contract_estimate in contract.contractestimate_set.all():
                estimated_hours += contract_estimate.duration

                if contract_estimate.contract_role:
                    contract_role_data[contract_estimate.contract_role.id] = {
                        'contract_role': contract_estimate.contract_role,
                        'performed_hours': Decimal('0.00'),
                        'estimated_hours': contract_estimate.duration,
                    }

            # Iterate over performance and fill in performed data
            for performance in performances:
                country = (performance.timesheet.user.userinfo.country
                        if (performance.timesheet.user.userinfo and performance.timesheet.user.userinfo.country)
                        else 'Other')
                if country not in country_data:
                    country_data[country] = {
                        'country': country,
                        'performed_hours': Decimal('0.00'),
                    }

                user = performance.timesheet.user
                if user.id not in user_data:
                    user_data[user.id] = {
                        'user': user,
                        'performed_hours': Decimal('0.00'),
                    }

                month = date(performance.timesheet.year, performance.timesheet.month, 1)
                if month not in month_data:
                    month_data[month] = {
                        'month': month.strftime('%Y-%m'),
                        'performed_hours': Decimal('0.00'),
                    }

                contract_role = performance.contract_role
                if contract_role.id not in contract_role_data:
                    contract_role_data[contract_role.id] = {
                        'contract_role': contract_role,
                        'performed_hours': Decimal('0.00'),
                        'estimated_hours': Decimal('0.00'),
                    }

                duration = performance.normalized_duration
                performed_hours += duration
                contract_role_data[performance.contract_role.id]['performed_hours'] += duration
                country_data[country]['performed_hours'] += duration
                user_data[user.id]['performed_hours'] += duration
                month_data[month]['performed_hours']+= duration

            # Iterate over contract role, user, country data and calculate performed_pct
            for contract_role_id, item in contract_role_data.items():
                item['performed_pct'] = round((item['performed_hours'] / performed_hours) * 100, 2) if performed_hours else None
                item['estimated_pct'] = round((item['performed_hours'] / item['estimated_hours']) * 100, 2) if item['estimated_hours'] else None
            for user_id, item in user_data.items():
                item['performed_pct'] = round((item['performed_hours'] / performed_hours) * 100, 2) if performed_hours else None
            for country, item in country_data.items():
                item['performed_pct'] = round((item['performed_hours'] / performed_hours) * 100, 2) if performed_hours else None
            for month, item in month_data.items():
                item['performed_pct'] = round((item['performed_hours'] / performed_hours) * 100, 2) if performed_hours else None

            # Fetch invoiced amount
            invoiced_amount = (models.InvoiceItem.objects
                    .filter(invoice__contract=contract)
                    .aggregate(invoiced_amount=Sum(F('price') * F('amount'),
                                                   output_field=DecimalField(max_digits=9, decimal_places=2))))['invoiced_amount']
            invoiced_amount = invoiced_amount if invoiced_amount else Decimal('0.00')

            # Attachments
            for attachment in contract.attachments.all():
                attachment_data[attachment.name] = {
                            'file': attachment.file,
                            'url': attachment.get_file_url(),
                    }

            data.append({
                'contract': contract,
                'contract_roles': contract_role_data.values(),
                'countries': country_data.values(),
                'users': user_data.values(),
                'months': sorted(month_data.values(), key=lambda i: i['month']),
                'performed_hours': performed_hours,
                'estimated_hours': estimated_hours,
                'estimated_pct': round((performed_hours / estimated_hours) * 100, 2) if estimated_hours else None,
                'invoiced_amount': invoiced_amount,
                'invoiced_pct': round((invoiced_amount / contract.fixed_fee) * 100, 2) if contract.fixed_fee else None,
                'attachments': attachment_data,
            })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.ProjectContractOverviewTable(data, order_by='contract')
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('Project contract overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/project_contract_overview.pug', context)


@staff_member_required
def admin_report_user_overtime_overview_view(request):
    """User overtime overview report."""
    fltr = filters.AdminReportUserOvertimeOverviewFilter(request.GET, models.LeaveDate.objects
                                                         .filter(leave__status=models.STATUS_APPROVED))
    user = get_object_or_404(auth_models.User.objects,
                             pk=request.GET.get('user', None), is_active=True) if request.GET.get('user') else None
    from_date = parser.parse(request.GET.get('from_date', None)).date() if request.GET.get('from_date') else None
    until_date = parser.parse(request.GET.get('until_date', None)).date() if request.GET.get('until_date') else None
    data = []

    overtime_leave_type_ids = list(models.LeaveType.objects.filter(overtime=True).values_list('id', flat=True))

    if user and from_date and until_date and (until_date >= from_date) and overtime_leave_type_ids:
        # Grab leave dates, index them by year, then month, then leave type ID
        leave_dates = fltr.qs.filter(leave__leave_type__id__in=overtime_leave_type_ids).select_related('leave')
        leave_date_data = {}
        for leave_date in leave_dates:
            (leave_date_data
                .setdefault(leave_date.starts_at.year, {})
                .setdefault(leave_date.starts_at.month, [])
                .append(leave_date))

        # Iterate over years, months to create monthly data
        current_date = copy.deepcopy(from_date)
        remaining_overtime_hours = Decimal('0.00')

        while current_date.strftime('%Y%m') <= until_date.strftime('%Y%m'):
            current_date_range = month_date_range(current_date.year, current_date.month)
            month_range_info = calculation.get_range_info([user], from_date=current_date_range[0],
                                                          until_date=current_date_range[1])

            overtime_hours = month_range_info[user.id]['overtime_hours']
            remaining_overtime_hours += overtime_hours

            remaining_hours = month_range_info[user.id]['remaining_hours']
            remaining_overtime_hours -= remaining_hours

            used_overtime_hours = sum([Decimal(str(round((x.ends_at - x.starts_at).total_seconds() / 3600, 2)))
                                      for x in leave_date_data.get(current_date.year, {}).get(current_date.month, {})])
            remaining_overtime_hours -= used_overtime_hours

            data.append({
                'year': current_date.year,
                'month': current_date.month,
                'user': user,
                'overtime_hours': overtime_hours,
                'remaining_hours': remaining_hours,
                'used_overtime_hours': used_overtime_hours,
                'remaining_overtime_hours': remaining_overtime_hours,
            })

            current_date += relativedelta(months=1)

    config = RequestConfig(request, paginate=False)
    table = tables.UserOvertimeOverviewTable(data)
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('User overtime overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/user_overtime_overview.pug', context)


@staff_member_required
def admin_report_expiring_support_contract_overview_view(request):
    """Expiring support contract overview report."""
    fltr = filters.AdminReportExpiringSupportContractOverviewFilter(request.GET,
                                                                    models.SupportContract.objects)
    company = request.GET.getlist('company', [])
    filter_internal = request.GET.get('filter_internal')
    data = []
    data_yearly_fixed = []
    data_yearly_performances = []
    data_monthly_fixed = []
    data_free = []
    data_consultancy = []


    contracts = (
        models.SupportContract.objects.all()
        .select_related('customer')
        .filter(active=True)
    )

    if company:
        contracts = contracts.filter(company__in=company)

    if filter_internal == "show_noninternal":
        contracts = contracts.exclude(customer=F('company'))
    elif filter_internal == "show_internal":
        contracts = contracts.filter(customer=F('company'))
    elif filter_internal == "show_all" or filter_internal == "":
        # Do nothing - show all. (#readability_counts)
        pass

    for contract in contracts:
        #performed_hours = (models.ActivityPerformance.objects
        #                   .filter(contract=contract)
        #                   .aggregate(performed_hours=Sum(F('duration') * F('performance_type__multiplier'))))['performed_hours']
        #performed_hours = performed_hours if performed_hours else Decimal('0.00')

        last_invoiced_period = (models.Invoice.objects
                                .filter(contract=contract)
                                .aggregate(Max('period_ends_at'))['period_ends_at__max']
                                )

        if contract.fixed_fee_period == 'yearly' and contract.day_rate == 0:
            data_yearly_fixed.append({
                'contract': contract,
                #'performed_hours': performed_hours,
                'last_invoiced_period': last_invoiced_period,
            })
        elif contract.fixed_fee_period == 'yearly' and contract.day_rate != 0:
            data_yearly_performances.append({
                'contract': contract,
                #'performed_hours': performed_hours,
                'last_invoiced_period': last_invoiced_period,
            })
        elif contract.fixed_fee_period == 'monthly' and contract.day_rate == 0:
            data_monthly_fixed.append({
                'contract': contract,
                #'performed_hours': performed_hours,
                'last_invoiced_period': last_invoiced_period,
            })
        elif contract.fixed_fee == 0 and contract.day_rate == 0:
            data_free.append({
                'contract': contract,
                #'performed_hours': performed_hours,
                'last_invoiced_period': last_invoiced_period,
            })
        elif contract.day_rate != 0:
            data_consultancy.append({
                'contract': contract,
                #'performed_hours': performed_hours,
                'last_invoiced_period': last_invoiced_period,
            })
        else:
            data.append({
                'contract': contract,
                #'performed_hours': performed_hours,
                'last_invoiced_period': last_invoiced_period,
            })

    config = RequestConfig(request, paginate=False)

    # data
    table = tables.ExpiringSupportContractOverviewTable(data, order_by='contract')
    config.configure(table)

    # data_yearly_fixed
    yearly_fixed_table = tables.ExpiringSupportContractOverviewTable(data_yearly_fixed, order_by='contract')
    config.configure(yearly_fixed_table)

    # data_yearly_performances
    yearly_performances_table= tables.ExpiringSupportContractOverviewTable(data_yearly_performances, order_by='contract')
    config.configure(yearly_performances_table)

    # data_monthly_fixed
    monthly_fixed_table = tables.ExpiringSupportContractOverviewTable(data_monthly_fixed, order_by='contract')
    config.configure(monthly_fixed_table)

    # data_free
    free_table = tables.ExpiringSupportContractOverviewTable(data_free, order_by='contract')
    config.configure(free_table)

    # data_consultancy
    consultancy_table = tables.ExpiringSupportContractOverviewTable(data_consultancy, order_by='contract')
    config.configure(consultancy_table)

    context = {
        'title': _('Expiring support contract overview'),
        'filter': fltr,
        'content': [ { 'subtitle': _('Monthly Billable performances'),
                       'subtable': consultancy_table },
                     { 'subtitle': _('Monthly Billable fixed fee'),
                       'subtable': monthly_fixed_table },
                     { 'subtitle': _('Yearly Billable Performances'),
                       'subtable': yearly_performances_table },
                     { 'subtitle': _('Yearly Billable fixed fee'),
                       'subtable': yearly_fixed_table },
                     { 'subtitle': _('Non-Billable'),
                       'subtable': free_table },
                     { 'subtitle': _('Other'),
                       'subtable': table },
                   ]
    }

    return render(request, 'ninetofiver/admin/reports/expiring_support_contract_overview.pug', context)


@staff_member_required
def admin_report_project_contract_budget_overview_view(request):
    """Project contract budget overview report."""
    fltr = filters.AdminReportProjectContractOverviewFilter(request.GET, models.ProjectContract.objects)
    data = []

    if True in map(bool, list(fltr.data.values())):
        contracts = (fltr.qs.all()
                    .select_related('customer')
                    .filter()
                    # Ensure contracts where the internal company and the customer are the same are filtered out
                    # These are internal contracts to cover things such as meetings, talks, etc..
                    .exclude(customer=F('company')))

        for contract in contracts:
            performed_hours = (models.ActivityPerformance.objects
                                .filter(contract=contract)
                                .aggregate(performed_hours=Sum(F('duration') * F('performance_type__multiplier'))))['performed_hours']
            performed_hours = performed_hours if performed_hours else Decimal('0.00')

            estimated_hours = (models.ContractEstimate.objects
                                .filter(contract=contract)
                                .aggregate(estimated_hours=Sum('duration')))['estimated_hours']
            estimated_hours = estimated_hours if estimated_hours else Decimal('0.00')

            invoiced_amount = (models.InvoiceItem.objects
                                .filter(invoice__contract=contract)
                                .aggregate(invoiced_amount=Sum(F('price') * F('amount'),
                                            output_field=DecimalField(max_digits=9, decimal_places=2))))['invoiced_amount']
            invoiced_amount = invoiced_amount if invoiced_amount else Decimal('0.00')

            data.append({
                'contract': contract,
                'performed_hours': performed_hours,
                'estimated_hours': estimated_hours,
                'estimated_pct': round((performed_hours / estimated_hours) * 100, 2) if estimated_hours else None,
                'invoiced_amount': invoiced_amount,
                'invoiced_pct': round((invoiced_amount / contract.fixed_fee) * 100, 2) if contract.fixed_fee else None,
            })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.ProjectContractBudgetOverviewTable(data, order_by='-performed')
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('Project contract budget overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/project_contract_budget_overview.pug', context)


@staff_member_required
def admin_report_expiring_user_training_overview_view(request):
    """Expiring user training overview report."""
    fltr = filters.AdminReportExpiringUserTrainingOverviewFilter(request.GET, models.Training.objects)

    ends_at_lte = (parser.parse(request.GET.get('ends_at_lte', None)).date()
                   if request.GET.get('ends_at_lte') else None)
    data = []

    # This SHOULD? work in Postgres if ever needed
    # trainings = (models.Training.objects.all()
    #              .select_related('training_type', 'user_training', 'user_training__user')
    #              .distinct('training_type', 'user_training')
    #              .order_by('-ends_at')
    #              )

    # But because MySQL doesn't know DISTINCT ON, we need to hack around.
    selected = {}
    training_pks = models.Training.objects.values("id", "user_training", "training_type").order_by("-ends_at")
    for record in training_pks:
        if (record.get('user_training'), record.get('training_type')) in selected:
            continue
        selected[(record.get('user_training'), record.get('training_type'))] = record.get('id')

    # And then fetch them with related stuff + we can now use additional filtering.
    if ends_at_lte:
        trainings = (models.Training.objects.filter(pk__in=selected.values(), ends_at__lte=ends_at_lte)
                     .select_related('training_type', 'user_training', 'user_training__user')
                     .order_by('-ends_at'))
    else:
        trainings = (models.Training.objects.filter(pk__in=selected.values())
                     .select_related('training_type', 'user_training', 'user_training__user')
                     .order_by('-ends_at'))

    for training in trainings:
        data.append({
            'training': training,
        })

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size})
    table = tables.ExpiringUserTrainingOverviewTable(data, order_by='ends_at')
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('Expiring user training overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/expiring_user_training_overview.pug', context)


@staff_member_required
def admin_report_internal_availability_overview_view(request):
    """Internal availability overview report."""
    data = []
    fltr = filters.AdminReportInternalAvailabilityOverviewFilter(request.GET, models.Timesheet.objects)
    date = parser.parse(request.GET.get('date', None)).date() if request.GET.get('date') else None

    users = auth_models.User.objects.filter(is_active=True).distinct()
    try:
        user_ids = list(map(int, request.GET.getlist('user', [])))
        users = users.filter(id__in=user_ids) if user_ids else users
    except Exception:
        pass
    try:
        group_ids = list(map(int, request.GET.getlist('group', [])))
        users = users.filter(groups__in=group_ids) if group_ids else users
    except Exception:
        pass

    try:
        contract_ids = list(map(int, request.GET.getlist('contract', [])))
        users = users.filter(contractuser__contract__in=contract_ids) if contract_ids else users
    except Exception:
        pass

    if users and date:
        # Fetch availability
        availability = calculation.get_internal_availability_info(users, date, date)

        # # Fetch contract user work schedules
        contract_user_work_schedules = (models.ContractUserWorkSchedule.objects
                                        .filter(contract_user__user__in=users)
                                        .filter(Q(ends_at__isnull=True, starts_at__lte=date) |
                                                Q(ends_at__isnull=False, starts_at__lte=date,
                                                  ends_at__gte=date))
                                        .select_related('contract_user', 'contract_user__user',
                                                        'contract_user__contract_role', 'contract_user__contract',
                                                        'contract_user__contract__customer'))
        # Index contract user work schedules by user
        contract_user_work_schedule_data = {}
        for contract_user_work_schedule in contract_user_work_schedules:
            (contract_user_work_schedule_data
                .setdefault(contract_user_work_schedule.contract_user.user.id, [])
                .append(contract_user_work_schedule))

        # Fetch employment contracts
        employment_contracts = (models.EmploymentContract.objects
                                .filter(
                                    (Q(ended_at__isnull=True) & Q(started_at__lte=date)) |
                                    (Q(started_at__lte=date) & Q(ended_at__gte=date)),
                                    user__in=users)
                                .order_by('started_at')
                                .select_related('user', 'company', 'work_schedule'))
        # Index employment contracts by user ID
        employment_contract_data = {}
        for employment_contract in employment_contracts:
            (employment_contract_data
                .setdefault(employment_contract.user.id, [])
                .append(employment_contract))

        # Iterate over users, days to create daily user data
        for user in users:

            user_data = {
                'user': user,
                'issues': {},
                'days': {},
            }
            data.append(user_data)

            date_str = str(date)
            user_day_data = user_data['days'][date_str] = {}

            day_availability = availability[str(user.id)][date_str]

            if day_availability == ['not_available_for_internal_work']:
                data.remove(user_data)
                continue

            day_contract_user_work_schedules = []
            day_scheduled_hours = Decimal('0.00')
            day_work_hours = Decimal('0.00')

            # Get contract user work schedules for this day
            # This allows us to determine the scheduled hours for this user
            for contract_user_work_schedule in contract_user_work_schedule_data.get(user.id, []):
                if (contract_user_work_schedule.starts_at <= date) and \
                        ((not contract_user_work_schedule.ends_at) or
                            (contract_user_work_schedule.ends_at >= date)):
                    day_contract_user_work_schedules.append(contract_user_work_schedule)
                    day_scheduled_hours += getattr(contract_user_work_schedule,
                                                   date.strftime('%A').lower(), Decimal('0.00'))

            # Get employment contract for this day
            # This allows us to determine the required hours for this user
            employment_contract = None
            try:
                for ec in employment_contract_data[user.id]:
                    if (ec.started_at <= date) and ((not ec.ended_at) or (ec.ended_at >= date)):
                        employment_contract = ec
                        break
            except KeyError:
                pass

            work_schedule = employment_contract.work_schedule if employment_contract else None
            if work_schedule:
                day_work_hours = getattr(work_schedule, date.strftime('%A').lower(), Decimal('0.00'))

            user_day_data['availability'] = day_availability
            user_day_data['contract_user_work_schedules'] = day_contract_user_work_schedules
            user_day_data['scheduled_hours'] = day_scheduled_hours
            user_day_data['work_hours'] = day_work_hours
            user_day_data['enough_hours'] = day_scheduled_hours >= day_work_hours
            free_hours = day_work_hours - day_scheduled_hours
            user_day_data['free_hours'] = free_hours
            user_day_data['available_for_internal'] = free_hours >= 1

            if (not user_data['issues']) and (user_day_data['available_for_internal'] is True):
                issues = {
                    'count': 0,
                    'results': [],
                }
                redmine_data = redmine.get_user_redmine_issues(user)
                issues['results'] += redmine_data
                issues['count'] = len(issues['results'])
                user_data['issues'] = issues

            if 'results' in user_data['issues']:
                for issue in user_data['issues']['results']:
                    redmine_con = redmine.get_redmine_connector()
                    fetch_issue = redmine_con.issue.get(issue.id)
                    issue['internal_status'] = []
                    if date == datetime.today().date():
                        if (getattr(fetch_issue, "start_date", None)
                            and fetch_issue.start_date
                            and (fetch_issue.start_date <= date)
                            and (fetch_issue.updated_on >= datetime.now() - timedelta(days=1))
                            # issue.status.id 2 for IP, 9 for RFUT
                            ):
                            if fetch_issue.status.id in [2, 9]:
                                user_day_data['availability'].append('green')
                                issue['internal_status'] = 'green'
                            else:
                                user_day_data['availability'].append('yellow')
                                issue['internal_status'] = 'yellow'
                        else:
                            user_day_data['availability'].append('red')
                            issue['internal_status'] = 'red'
                    else:
                        if(
                           # no expected_ready atm but is that for our estimates (we can use est hours) or client's
                           # what is 'on hold'?
                           ('due_date' in fetch_issue and fetch_issue.due_date >= date)
                           and (fetch_issue.updated_on >= date - timedelta(days=1))
                           ):
                            user_day_data['availability'].append('green')
                            issue['internal_status'] = 'green'
                        else:
                            user_day_data['availability'].append('red')
                            issue['internal_status'] = 'red'

    config = RequestConfig(request, paginate={'per_page': pagination.CustomizablePageNumberPagination.page_size * 4})
    table = tables.InternalAvailabilityOverviewTable(date, date, data)
    config.configure(table)

    export_format = request.GET.get('_export', None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response('table.{}'.format(export_format))

    context = {
        'title': _('Internal availability overview'),
        'table': table,
        'filter': fltr,
    }

    return render(request, 'ninetofiver/admin/reports/internal_availability_overview.pug', context)


class AdminTimesheetContractPdfExportView(BaseTimesheetContractPdfExportServiceAPIView):
    """Export a timesheet contract to PDF."""

    permission_classes = (permissions.IsAdminUser,)

    def resolve_user_timesheet_contracts(self, context):
        """Resolve users, timesheets and contracts for this report."""
        data = context.get('user_timesheet_contract_pks', None)
        data = [list(map(int, x.split(':'))) for x in data.split(',')]

        for item in data:
            item[0] = get_object_or_404(auth_models.User.objects.filter().distinct(), pk=item[0])
            item[1] = get_object_or_404(models.Timesheet.objects.filter().distinct(), pk=item[1], user=item[0])
            item[2] = get_object_or_404(models.Contract.objects.filter().distinct(), pk=item[2])

        return data
