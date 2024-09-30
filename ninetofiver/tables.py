"""Tables."""
import uuid
from datetime import timedelta, date, datetime

import django_tables2 as tables
import humanize
import six
from django.template import Context, Template
from django.template.loader import get_template
from django.urls import reverse
from django.utils.html import format_html, strip_tags
from django.utils.translation import gettext_lazy as _
from django_tables2.export.export import TableExport
from django_tables2.utils import A

from ninetofiver import models
from ninetofiver.utils import month_date_range, format_duration, dates_in_range
from math import floor

class TemplateMixin(object):
    """
    Inspired by TemplateColumn, this can be used to add wrapping template to any column as mixin.
    Example:
        TemplatedEuroColumn(TemplateMixin, EuroColumn)

    Arguments:
        pre_template_code (str): template code to render
        pre_template_name (str): name of the template to render
        post_template_code (str): template code to render
        post_template_name (str): name of the template to render
        extra_context (dict): optional extra template context

    A `~django.template.Template` object is created from the
    *template_code* or *template_name* and rendered with a context containing:

    - *record*      -- data record for the current row
    - *value*       -- value from `record` that corresponds to the current column
    - *default*     -- appropriate default value to use as fallback.
    - *row_counter* -- The number of the row this cell is being rendered in.
    - any context variables passed using the `extra_context` argument to `TemplateColumn`.

    Example:

    .. code-block:: python

        class ExampleTable(tables.Table):
            foo = TemplatedEuroColumn(post_template_code: '<div style:'color: red'>', post_template_code:'</div>')

    """

    def __init__(self,
                 *args,
                 pre_template_code=None,
                 pre_template_name=None,
                 post_template_code=None,
                 post_template_name=None,
                 extra_context=None,
                 **kwargs
                 ):
        self.pre_template_code = pre_template_code
        self.pre_template_name = pre_template_name
        self.post_template_code = post_template_code
        self.post_template_name = post_template_name
        self.extra_context = extra_context or {}

        super(TemplateMixin, self).__init__(*args, **kwargs)

    def render(self, record, table, value, bound_column, **kwargs):
        # If the table is being rendered using `render_table`, it hackily
        # attaches the context to the table as a gift to `TemplateColumn`.
        context = getattr(table, "context", Context())
        context.update(self.extra_context)
        context.update(
            {
                "default": bound_column.default,
                "column": bound_column,
                "record": record,
                "value": value,
                "row_counter": kwargs["bound_row"].row_counter,
            }
        )

        pre_html = ""
        post_html = ""
        try:
            if self.pre_template_code:
                pre_html = Template(self.pre_template_code).render(context)
            elif self.pre_template_name:
                pre_html = get_template(self.pre_template_name).render(context.flatten())

            if self.post_template_code:
                post_html = Template(self.post_template_code).render(context)
            elif self.post_template_name:
                pre_html = get_template(self.post_template_name).render(context.flatten())
        finally:
            context.pop()

        in_html = super(TemplateMixin, self).render(value)
        return format_html('{}{}{}', pre_html, in_html, post_html)

    def value(self, **kwargs):
        html = super(TemplateMixin, self).value(**kwargs)
        if isinstance(html, six.string_types):
            return strip_tags(html)
        else:
            return html


class BaseTable(tables.Table):
    """Base table."""

    # export_formats = TableExport.FORMATS
    export_formats = [
        TableExport.CSV,
        TableExport.JSON,
        TableExport.ODS,
        TableExport.XLS,
    ]

    class Meta:
        template_name = 'django_tables2/bootstrap4.html'
        attrs = {'class': 'table table-bordered table-striped table-hover', 'container': 'table-responsive'}


class HoursColumn(tables.Column):
    """Hours column."""

    def render(self, value):
        """Render the value."""
        res = format_duration(value)

        if not value:
            res = format_html('<span style="color:#999;">{}</span>', res)

        return res

    def value(self, value):
        """Return the value."""
        return value


class EuroColumn(tables.Column):
    """Euro column."""

    attrs = {'td': {'align': 'right', 'class': 'text-nowrap'}}

    def render(self, value):
        if value:
            return '€ {}'.format(humanize.intcomma(value))
        else:
            return format_html('<span style="color:#999;">{}</span>', '€ {}'.format(humanize.intcomma(value)))

    def value(self, value):
        return value


class InvoiceColoredEuroColumn(TemplateMixin, EuroColumn):
    """Colored Euro column for Invoiced Consultancy Contract Overview."""

    # Hack, normally methods should have self as the first parameters. This is fine.
    # noinspection PyMethodParameters
    def determine_invoiced_cell_color(record):
        invoiced = record['invoiced']
        to_be_invoiced = record['to_be_invoiced']
        if invoiced >= to_be_invoiced:
            return 'table-success'
        elif invoiced == 0 and to_be_invoiced != 0:
            return 'table-danger'
        elif invoiced != 0 and to_be_invoiced != 0 and invoiced < to_be_invoiced:
            return 'table-warning'
        elif to_be_invoiced == 0:
            return

    def determine_invoiced_style(record):
        invoiced = record['invoiced']
        to_be_invoiced = record['to_be_invoiced']
        if invoiced > to_be_invoiced:
            return 'font-weight: bold'
        else:
            return 'font-weight: normal'

    attrs = {'td': {'align': 'right', 'class': determine_invoiced_cell_color, 'style': determine_invoiced_style}}


class BarChartComparisonColumn(tables.TemplateColumn):
    """Bar chart comparison column."""

    def __init__(self, dataset=[], yLabel=None, **kwargs):
        """Constructor."""
        kwargs['template_name'] = 'ninetofiver/admin/reports/bar_chart_comparison_column.pug'
        kwargs['extra_context'] = {
            'yLabel': yLabel,
            'dataset': dataset,
        }

        super().__init__(**kwargs)

    def render(self, record, table, value, bound_column, **kwargs):
        self.extra_context['uniqueId'] = str(uuid.uuid4())

        for item in self.extra_context['dataset']:
            if item.get('accessor', None):
                item['value'] = item['accessor'].resolve(record)

        self.extra_context['title'] = '%s vs. %s: %s' % (self.extra_context['dataset'][0]['label'],
                                                         self.extra_context['dataset'][1]['label'],
                                                         ('%s%%' % round((self.extra_context['dataset'][0]['value'] / self.extra_context['dataset'][1]['value']) * 100, 2)
                                                          if self.extra_context['dataset'][1]['value'] else 'n/a'))

        return super().render(record, table, value, bound_column, **kwargs)

    def value(self, record, table, value, bound_column, **kwargs):
        return bound_column.accessor.resolve(record)

    def render_footer(self, table, column, bound_column, **kwargs):
        self.extra_context['uniqueId'] = str(uuid.uuid4())

        for item in self.extra_context['dataset']:
            if item.get('accessor', None):
                item['value'] = sum([item['accessor'].resolve(record) for record in table.data])

        self.extra_context['title'] = 'Total: %s vs. %s: %s' % (self.extra_context['dataset'][0]['label'],
                                                                self.extra_context['dataset'][1]['label'],
                                                                ('%s%%' % round((self.extra_context['dataset'][0]['value'] / self.extra_context['dataset'][1]['value']) * 100, 2)
                                                                 if self.extra_context['dataset'][1]['value'] else 'n/a'))

        return super().render(None, table, None, bound_column, bound_row=tables.rows.BoundRow(None, table))


class SummedHoursColumn(HoursColumn):
    """Summed hours column."""

    def render_footer(self, table, column, bound_column):
        """Render the footer."""
        accessor = self.accessor if self.accessor else A(bound_column.name)
        total = [accessor.resolve(x) for x in table.data]
        total = sum([x for x in total if x is not None])
        return format_html(_('Total: {}'), self.render(total))


class SummedEuroColumn(EuroColumn):
    """Summed euro column."""

    def render_footer(self, table, column, bound_column):
        """Render the footer."""
        accessor = self.accessor if self.accessor else A(bound_column.name)
        total = [accessor.resolve(x) for x in table.data]
        total = sum([x for x in total if x is not None])
        return format_html(_('<div align="right">Total: {}</div>'), self.render(total))


class SummedInvoiceColoredEuroColumn(InvoiceColoredEuroColumn):
    """Summed euro column."""

    def render_footer(self, table, column, bound_column):
        """Render the footer."""
        accessor = self.accessor if self.accessor else A(bound_column.name)
        total = [accessor.resolve(x) for x in table.data]
        total = sum([x for x in total if x is not None])
        return format_html(_('<div align="right">Total: {}</div>'), EuroColumn.render(self, total))


class TimesheetContractOverviewTable(BaseTable):
    """Timesheet contract overview table."""

    class Meta(BaseTable.Meta):
        pass

    user = tables.LinkColumn(
        viewname='admin:auth_user_change',
        args=[A('timesheet.user.id')],
        accessor='timesheet.user',
        order_by=['timesheet.user.first_name', 'timesheet.user.last_name', 'timesheet.user.username']
    )
    timesheet = tables.LinkColumn(
        viewname='admin:ninetofiver_timesheet_change',
        args=[A('timesheet.id')],
        order_by=['timesheet.year', 'timesheet.month']
    )
    status = tables.Column(
        accessor='timesheet.status'
    )
    contract = tables.LinkColumn(
        viewname='admin:ninetofiver_contract_change',
        args=[A('contract.id')],
        order_by=['contract.name']
    )
    duration = SummedHoursColumn(verbose_name='Duration (hours)')
    standby_days = tables.Column()

    def render_actions_footer(table, column, bound_column):
        buttons = []

        if table.data:
            # Determine filters for given data
            query = []
            years = []
            months = []
            users = []
            contracts = []
            for record in table.data:
                if record['timesheet'].year not in years:
                    years.append(record['timesheet'].year)
                if record['timesheet'].month not in months:
                    months.append(record['timesheet'].month)
                if record['timesheet'].user.id not in users:
                    users.append(record['timesheet'].user.id)
                if record['contract'].id not in contracts:
                    contracts.append(record['contract'].id)
            if years:
                query.append('timesheet__year__in=%s' % (','.join(map(str, years))))
            if months:
                query.append('timesheet__month__in=%s' % (','.join(map(str, months))))
            if users:
                query.append('timesheet__user__id__in=%s' % (','.join(map(str, users))))
            if contracts:
                query.append('contract__id__in=%s' % (','.join(map(str, contracts))))

            buttons.append(('<a class="button" href="%(url)s?%(query)s">Details</a>') % {
                'url': reverse('admin:ninetofiver_performance_changelist'),
                'query': '&'.join(query),
            })

            pks = ','.join(['%s:%s:%s' % (x['timesheet'].user.id, x['timesheet'].id, x['contract'].id)
                            for x in table.data])
            buttons.append('<a class="button" href="%s">PDF</a>' % reverse('admin_timesheet_contract_pdf_export',
                           kwargs={'user_timesheet_contract_pks': pks}))

        return format_html('%s' % ('&nbsp;'.join(buttons)))

    actions = tables.Column(accessor='timesheet', orderable=False, exclude_from_export=True,
                            footer=render_actions_footer)

    def render_actions(self, record):
        buttons = []
        buttons.append(('<a class="button" href="%(url)s?' +
                        'contract__id__exact=%(contract)s&' +
                        'timesheet__user__id__exact=%(user)s&' +
                        'timesheet__year=%(year)s&' +
                        'timesheet__month=%(month)s">Details</a>') % {
            'url': reverse('admin:ninetofiver_performance_changelist'),
            'contract': record['contract'].id,
            'user': record['timesheet'].user.id,
            'year': record['timesheet'].year,
            'month': record['timesheet'].month,
        })
        buttons.append('<a class="button" href="%s">PDF</a>' % reverse('admin_timesheet_contract_pdf_export', kwargs={
            'user_timesheet_contract_pks': '%s:%s:%s' % (record['timesheet'].user.id, record['timesheet'].id,
                                                         record['contract'].id),
        }))

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class TimesheetOverviewTable(BaseTable):
    """Timesheet overview table."""

    class Meta(BaseTable.Meta):
        pass

    user = tables.LinkColumn(
        viewname='admin:auth_user_change',
        args=[A('timesheet.user.id')],
        accessor='timesheet.user',
        order_by=['timesheet.user.first_name', 'timesheet.user.last_name', 'timesheet.user.username']
    )
    timesheet = tables.LinkColumn(
        viewname='admin:ninetofiver_timesheet_change',
        args=[A('timesheet.id')],
        order_by=['timesheet.year', 'timesheet.month']
    )
    status = tables.Column(accessor='timesheet.status')
    work_hours = SummedHoursColumn(accessor='range_info.work_hours')
    performed_hours = SummedHoursColumn(accessor='range_info.performed_hours')
    leave_hours = SummedHoursColumn(accessor='range_info.leave_hours')
    holiday_hours = SummedHoursColumn(accessor='range_info.holiday_hours')
    remaining_hours = SummedHoursColumn(accessor='range_info.remaining_hours')
    attachments = tables.Column(accessor='timesheet.attachments', orderable=False)
    percentage_complete_currmonth = tables.Column(accessor="range_info",orderable=False, verbose_name="% filled in (until today)")
    percentage_complete = tables.Column(accessor="range_info",orderable=False, verbose_name="% filled in (whole month)")
    actions = tables.Column(accessor='timesheet', orderable=False, exclude_from_export=True)
    
    def before_render(self,request):
        if int(self.request.GET.get("month")) != date.today().month or int(self.request.GET.get("year")) != date.today().year:
            self.columns.hide("percentage_complete_currmonth")
        
    def render_percentage_complete_currmonth(self,record,value,column):
        # today = date.today()
        # next_month = date.today().replace(day=28) + timedelta(days=4)
        # last = next_month - timedelta(days=next_month.day)
        # contract = models.EmploymentContract.objects.get(started_at__lte=f"{today.year}-{f'0{today.month}' if today.month < 10 else today.month}-01",ended_at__gte=f"{today.year}-{f'0{today.month}' if today.month < 10 else today.month}-{last.day}",user=record["timesheet"].user.id)
        try:
            perc = floor((100 - (record["range_info_to_day"]["remaining_hours"] / record["range_info_to_day"]["work_hours"] * 100))*10)/10
        except:
            perc = -1
        c = "244,85,85" if perc < 25 else "244,154,85" if perc < 50 else "244,231,85" if perc<75 else "165,244,85" if perc<90 else "67,232,55"
        if perc != -1:
            column.attrs = {'td':{'style':f"background-color: rgb({c});"}}
        return format_html(f'<p>{perc} %</p>' if perc != -1 else "<p></p>")
    
    def render_percentage_complete(self, record,value,column):
        try:
            perc = floor((100 - (record["range_info"]["remaining_hours"] / record["range_info"]["work_hours"] * 100))*10)/10
        except:
            perc = -1
        c = "244,85,85" if perc < 25 else "244,154,85" if perc < 50 else "244,231,85" if perc<75 else "165,244,85" if perc<90 else "67,232,55"
        if perc != -1:
            column.attrs = {'td':{'style':f"background-color: rgb({c});"}}
        return format_html(f'<p>{perc} %</p>' if perc != -1 else "<p></p>")

    def render_attachments(self, record):
        return format_html('<br>'.join('<a href="%s">%s</a>'
                           % (x.get_file_url(), str(x)) for x in list(record['timesheet'].attachments.all())))

    def value_attachments(self, record):
        return format_html('\n'.join('%s|%s'
                           % (x.get_file_url(), str(x)) for x in list(record['timesheet'].attachments.all())))

    def render_actions(self, record):
        buttons = []

        if record['timesheet'].status == models.STATUS_PENDING:
            buttons.append('<a class="button" href="%(url)s?return=true">Close</a>' % {
                'url': reverse('admin_timesheet_close', kwargs={'timesheet_pk': record['timesheet'].id}),
            })
            buttons.append('<a class="button" href="%(url)s?return=true">Reopen</a>' % {
                'url': reverse('admin_timesheet_activate', kwargs={'timesheet_pk': record['timesheet'].id}),
            })

        from_date, until_date = record['timesheet'].get_date_range()

        buttons.append(('<a class="button" href="%(url)s?' +
                        'user=%(user)s&' +
                        'from_date=%(from_date)s&' +
                        'until_date=%(until_date)s">Details</a>') % {
            'url': reverse('admin_report_user_range_info'),
            'user': record['timesheet'].user.id,
            'from_date': from_date.strftime('%Y-%m-%d'),
            'until_date': until_date.strftime('%Y-%m-%d'),
        })

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class UserRangeInfoTable(BaseTable):
    """User range info table."""

    class Meta(BaseTable.Meta):
        pass

    date = tables.DateColumn('D d/m/Y')
    work_hours = SummedHoursColumn(accessor='day_detail.work_hours')
    performed_hours = SummedHoursColumn(accessor='day_detail.performed_hours')
    leave_hours = SummedHoursColumn(accessor='day_detail.leave_hours')
    holiday_hours = SummedHoursColumn(accessor='day_detail.holiday_hours')
    remaining_hours = SummedHoursColumn(accessor='day_detail.remaining_hours')
    overtime_hours = SummedHoursColumn(accessor='day_detail.overtime_hours')

    def render_actions(self, record):
        buttons = []

        if record['day_detail']['performed_hours']:
            buttons.append(('<a class="button" href="%(url)s?' +
                            'timesheet__user__id__exact=%(user)s&' +
                            'timesheet__year=%(year)s&' +
                            'timesheet__month=%(month)s&' +
                            'date__range__lte=%(date)s&' +
                            'date__range__gte=%(date)s">Performance</a>') % {
                'url': reverse('admin:ninetofiver_performance_changelist'),
                'user': record['user'].id,
                'year': record['date'].year,
                'month': record['date'].month,
                'date': record['date'].strftime('%Y-%m-%d'),
            })

        if record['day_detail']['holiday_hours']:
            buttons.append(('<a class="button" href="%(url)s?' +
                            'date__range__gte=%(date)s&' +
                            'date__range__lte=%(date)s">Holidays</a>') % {
                'url': reverse('admin:ninetofiver_holiday_changelist'),
                'date': record['date'].strftime('%Y-%m-%d'),
            })

        if record['day_detail']['leave_hours']:
            buttons.append(('<a class="button" href="%(url)s?' +
                            'user__id__exact=%(user)s&' +
                            'status__exact=%(status)s&' +
                            'leavedate__starts_at__range__gte_0=%(leavedate__starts_at__range__gte_0)s&' +
                            'leavedate__starts_at__range__gte_1=%(leavedate__starts_at__range__gte_1)s&' +
                            'leavedate__starts_at__range__lte_0=%(leavedate__starts_at__range__lte_0)s&' +
                            'leavedate__starts_at__range__lte_1=%(leavedate__starts_at__range__lte_1)s">Leave</a>') % {
                'url': reverse('admin:ninetofiver_leave_changelist'),
                'user': record['user'].id,
                'status': models.STATUS_APPROVED,
                'leavedate__starts_at__range__gte_0': record['date'].strftime('%Y-%m-%d'),
                'leavedate__starts_at__range__gte_1': '00:00:00',
                'leavedate__starts_at__range__lte_0': record['date'].strftime('%Y-%m-%d'),
                'leavedate__starts_at__range__lte_1': '23:59:59',
            })

        return format_html('%s' % ('&nbsp;'.join(buttons)))

    def render_actions_footer(table, column, bound_column):

        users = []
        dates = []
        for record in table.data:
            if record['date'] not in dates:
                dates.append(record['date'])
            if record['user'].id not in users:
                users.append(record['user'].id)

        return format_html(('<a class="button" href="%(url)s?' +
                            'timesheet__user__id__exact=%(user)s&' +
                            'timesheet__year=%(year)s&' +
                            'timesheet__month=%(month)s&' +
                            'date__range__lte=%(end_date)s&' +
                            'date__range__gte=%(start_date)s">All performances</a>') % {
            'url': reverse('admin:ninetofiver_performance_changelist'),
            'user': users[0],
            'year': dates[0].year,
            'month': dates[0].month,
            'start_date': min(dates).strftime('%Y-%m-%d'),
            'end_date': max(dates).strftime('%Y-%m-%d'),
        })

    actions = tables.Column(accessor='date', orderable=False, exclude_from_export=True,
                            footer=render_actions_footer)


class UserGroupLeaveOverviewTable(BaseTable):
    """User leave overview table per group/company."""

    class Meta(BaseTable.Meta):
        pass

    user = tables.Column()
    actions = tables.Column(accessor='user', orderable=False, exclude_from_export=True)

    def __init__(self, *args, **kwargs):
        """Constructor."""
        # Create an additional column for every leave type
        extra_columns = []
        for leave_type in models.LeaveType.objects.order_by('name'):
            column = SummedHoursColumn(accessor=A('leave_type_hours.%s' % leave_type.name))
            extra_columns.append([leave_type.name, column])
        kwargs['extra_columns'] = extra_columns
        kwargs['sequence'] = ('user', '...', 'actions')
        super().__init__(*args, **kwargs)

    def render_actions(self, record):
        buttons = []

        buttons.append(('<a class="button" href="%(url)s?' +
                        'user=%(user)s&from_date=%(from_date)s&until_date=%(until_date)s">Leave</a>') % {
            'url': reverse('admin_report_user_leave_overview'),
            'user': record['user'].id,
            'from_date':record["from_date"].strftime('%Y-%m-%d'),
            'until_date':record['until_date'].strftime('%Y-%m-%d')
        })

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class UserLeaveOverviewTable(BaseTable):
    """User leave overview table."""

    class Meta(BaseTable.Meta):
        pass

    year = tables.Column()
    month = tables.Column()
    timesheet_status = tables.Column(accessor='timesheet.status')
    actions = tables.Column(accessor='user', orderable=False, exclude_from_export=True)

    def __init__(self, *args, **kwargs):
        """Constructor."""
        # Create an additional column for every leave type
        extra_columns = []
        for leave_type in models.LeaveType.objects.order_by('name'):
            column = SummedHoursColumn(accessor=A('leave_type_hours.%s' % leave_type.name))
            extra_columns.append([leave_type.name, column])
        kwargs['extra_columns'] = extra_columns
        kwargs['sequence'] = ('year', 'month', '...', 'actions')
        super().__init__(*args, **kwargs)

    def render_actions(self, record):
        buttons = []

        date_range = month_date_range(record['year'], record['month'])

        buttons.append(('<a class="button" href="%(url)s?' +
                        'user__id__exact=%(user)s&' +
                        'status__exact=%(status)s&' +
                        'leavedate__starts_at__gte_0=%(leavedate__starts_at__gte_0)s&' +
                        'leavedate__starts_at__gte_1=%(leavedate__starts_at__gte_1)s&' +
                        'leavedate__starts_at__lte_0=%(leavedate__starts_at__lte_0)s&' +
                        'leavedate__starts_at__lte_1=%(leavedate__starts_at__lte_1)s">Leave</a>') % {
            'url': reverse('admin:ninetofiver_leave_changelist'),
            'user': record['user'].id,
            'status': models.STATUS_APPROVED,
            'leavedate__starts_at__gte_0': date_range[0].strftime('%Y-%m-%d'),
            'leavedate__starts_at__gte_1': '00:00:00',
            'leavedate__starts_at__lte_0': date_range[1].strftime('%Y-%m-%d'),
            'leavedate__starts_at__lte_1': '23:59:59',
        })

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class UserWorkRatioByUserTable(BaseTable):
    """User work ratio overview table."""

    class Meta(BaseTable.Meta):
        pass

    year = tables.Column()
    month = tables.Column()
    work_hours = SummedHoursColumn()
    customer_hours = SummedHoursColumn()
    internal_hours = SummedHoursColumn()
    leaves = SummedHoursColumn()
    ratio = tables.Column(empty_values=())

    def render_ratio(self, record):
        total_hours = record['customer_hours'] + record['internal_hours'] + record['leaves']
        customer_hours_pct = round((record['customer_hours'] / (total_hours if total_hours else 1.0)) * 100, 2)
        internal_hours_pct = round((record['internal_hours'] / (total_hours if total_hours else 1.0)) * 100, 2)
        leaves_pct = round((record['leaves'] / (total_hours if total_hours else 1.0)) * 100, 2)
        res = '<div class="progress" style="min-width: 300px;">'
        res += '<div class="progress-bar bg-success" role="progressbar" style="width: {}%">{}%</div>'.format(
            customer_hours_pct, customer_hours_pct)
        res += '<div class="progress-bar bg-warning" role="progressbar" style="width: {}%">{}%</div>'.format(
            internal_hours_pct, internal_hours_pct)
        res += '<div class="progress-bar bg-secondary" role="progressbar" style="width: {}%">{}%</div>'.format(
            leaves_pct, leaves_pct)
        res += '</div>'
        return format_html(res)


class UserWorkRatioByMonthTable(BaseTable):
    """User work ratio overview table."""

    class Meta(BaseTable.Meta):
        pass

    user = tables.LinkColumn(
        viewname='admin:auth_user_change',
        args=[A('user.id')],
        accessor='user',
        order_by=['user.first_name', 'user.last_name', 'user.username']
    )
    work_hours = SummedHoursColumn()
    customer_hours = SummedHoursColumn()
    internal_hours = SummedHoursColumn()
    leaves = SummedHoursColumn()
    ratio = tables.Column(empty_values=())

    def render_ratio(self, record):
        total_hours = record['customer_hours'] + record['internal_hours'] + record['leaves']
        customer_hours_pct = round((record['customer_hours'] / (total_hours if total_hours else 1.0)) * 100, 2)
        internal_hours_pct = round((record['internal_hours'] / (total_hours if total_hours else 1.0)) * 100, 2)
        leaves_pct = round((record['leaves'] / (total_hours if total_hours else 1.0)) * 100, 2)
        res = '<div class="progress" style="min-width: 300px;">'
        res += '<div class="progress-bar bg-success" role="progressbar" style="width: {}%">{}%</div>'.format(
            customer_hours_pct, customer_hours_pct)
        res += '<div class="progress-bar bg-warning" role="progressbar" style="width: {}%">{}%</div>'.format(
            internal_hours_pct, internal_hours_pct)
        res += '<div class="progress-bar bg-secondary" role="progressbar" style="width: {}%">{}%</div>'.format(
            leaves_pct, leaves_pct)
        res += '</div>'
        return format_html(res)


class UserWorkRatioOverviewTable(BaseTable):
    """User work ratio overview table."""

    class Meta(BaseTable.Meta):
        pass

    year = tables.Column()
    month = tables.Column()
    total_hours = SummedHoursColumn()
    consultancy_hours = SummedHoursColumn()
    project_hours = SummedHoursColumn()
    support_hours = SummedHoursColumn()
    leave_hours = SummedHoursColumn()
    consultancy_pct = tables.Column(attrs={'th': {'class': 'bg-success'}})
    project_pct = tables.Column(attrs={'th': {'class': 'bg-info'}})
    support_pct = tables.Column(attrs={'th': {'class': 'bg-warning'}})
    leave_pct = tables.Column(attrs={'th': {'class': 'bg-secondary'}})
    ratio = tables.Column(accessor='user', orderable=False, exclude_from_export=True)
    actions = tables.Column(accessor='user', orderable=False, exclude_from_export=True)

    def render_ratio(self, record):
        res = ('<div class="progress" style="min-width: 300px;">' +
               '<div class="progress-bar bg-success" role="progressbar" style="width: %(consultancy_pct)s%%">%(consultancy_pct)s%%</div>' +
               '<div class="progress-bar bg-info" role="progressbar" style="width: %(project_pct)s%%">%(project_pct)s%%</div>' +
               '<div class="progress-bar bg-warning" role="progressbar" style="width: %(support_pct)s%%">%(support_pct)s%%</div>' +
               '<div class="progress-bar bg-secondary" role="progressbar" style="width: %(leave_pct)s%%">%(leave_pct)s%%</div>' +
               '</div>') % record

        return format_html(res)

    def render_actions(self, record):
        buttons = []

        date_range = month_date_range(record['year'], record['month'])

        if record['consultancy_hours'] or record['project_hours'] or record['support_hours']:
            buttons.append(('<a class="button" href="%(url)s?' +
                            'timesheet__user__id__exact=%(user)s&' +
                            'timesheet__year=%(year)s&' +
                            'timesheet__month=%(month)s">Performance</a>') % {
                'url': reverse('admin:ninetofiver_performance_changelist'),
                'user': record['user'].id,
                'year': record['year'],
                'month': record['month'],
            })

        if record['leave_hours']:
            buttons.append(('<a class="button" href="%(url)s?' +
                            'user__id__exact=%(user)s&' +
                            'status__exact=%(status)s&' +
                            'leavedate__starts_at__range__gte_0=%(leavedate__starts_at__range__gte_0)s&' +
                            'leavedate__starts_at__range__gte_1=%(leavedate__starts_at__range__gte_1)s&' +
                            'leavedate__starts_at__range__lte_0=%(leavedate__starts_at__range__lte_0)s&' +
                            'leavedate__starts_at__range__lte_1=%(leavedate__starts_at__range__lte_1)s">Leave</a>') % {
                'url': reverse('admin:ninetofiver_leave_changelist'),
                'user': record['user'].id,
                'status': models.STATUS_APPROVED,
                'leavedate__starts_at__range__gte_0': date_range[0].strftime('%Y-%m-%d'),
                'leavedate__starts_at__range__gte_1': '00:00:00',
                'leavedate__starts_at__range__lte_0': date_range[1].strftime('%Y-%m-%d'),
                'leavedate__starts_at__range__lte_1': '23:59:59',
            })

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class ResourceAvailabilityDayColumn(tables.TemplateColumn):
    """Resource availability day column."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        kwargs['template_name'] = 'ninetofiver/admin/reports/resource_availability_overview_day.pug'
        super().__init__(*args, **kwargs)


class MonthlyResourceAvailabilityDayColumn(tables.TemplateColumn):
    """Timesheet monthly overview day column."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        kwargs['template_name'] = 'ninetofiver/admin/reports/timesheet_monthly_overview_day.pug'
        super().__init__(*args, **kwargs)

    def value(self, **kwargs):
        html = super(MonthlyResourceAvailabilityDayColumn, self).value(**kwargs)
        return html.strip()


class ResourceAvailabilityOverviewTable(BaseTable):
    """Resource availability overview table."""

    export_formats = []

    class Meta(BaseTable.Meta):
        pass

    user = tables.LinkColumn(
        viewname='admin:auth_user_change',
        args=[A('user.id')],
        accessor='user',
        order_by=['user.first_name', 'user.last_name', 'user.username']
    )

    def __init__(self, from_date, until_date, *args, **kwargs):
        """Constructor."""
        # Create an additional column for every leave type
        extra_columns = []
        if from_date and until_date:
            for day_date in dates_in_range(from_date, until_date):
                date_str = str(day_date)
                column = ResourceAvailabilityDayColumn(accessor=A('days.%s' % date_str), orderable=False)
                extra_columns.append([day_date.strftime('%a, %d %b'), column])
        kwargs['extra_columns'] = extra_columns
        kwargs['sequence'] = ('user', '...')
        super().__init__(*args, **kwargs)


class InternalAvailabilityDayColumn(tables.TemplateColumn):
    """Internal availability day column."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        kwargs['template_name'] = 'ninetofiver/admin/reports/internal_availability_overview_day.pug'
        super().__init__(*args, **kwargs)


class InternalAvailabilityIssuesColumn(tables.TemplateColumn):
    """Internal availability issues column."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        kwargs['template_name'] = 'ninetofiver/admin/reports/internal_availability_overview_issues.pug'
        super().__init__(*args, **kwargs)


class InternalAvailabilityOverviewTable(BaseTable):
    """Internal availability overview table."""

    export_formats = []

    class Meta(BaseTable.Meta):
        pass

    user = tables.LinkColumn(
        viewname='admin:auth_user_change',
        args=[A('user.id')],
        accessor='user',
        order_by=['user.first_name', 'user.last_name', 'user.username']
    )

    def __init__(self, from_date, until_date, *args, **kwargs):
        """Constructor."""
        # Create an additional column for every availability type
        extra_columns = []
        if from_date and until_date:
            for day_date in dates_in_range(from_date, until_date):
                date_str = str(day_date)
                column = InternalAvailabilityDayColumn(accessor=A('days.%s' % date_str), orderable=False)
                extra_columns.append([day_date.strftime('%a, %d %b'), column])

        # Add issues if present
        if any('issues' in x for x in args[0]):
            column = InternalAvailabilityIssuesColumn(accessor=('issues'))
            extra_columns.append(['Issues', column])

        kwargs['extra_columns'] = extra_columns
        kwargs['sequence'] = ('user', '...')
        super().__init__(*args, **kwargs)


class TimesheetMonthlyOverviewTable(BaseTable):
    """Timesheet monthly overview table."""

    class Meta(BaseTable.Meta):
        pass

    user = tables.LinkColumn(
        viewname='admin:auth_user_change',
        args=[A('user.id')],
        accessor='user',
        order_by=['user.first_name', 'user.last_name', 'user.username']
    )

    def __init__(self, from_date, until_date, *args, **kwargs):
        """Constructor."""
        # Create an additional column for every leave type
        extra_columns = []
        if from_date and until_date:
            for day_date in dates_in_range(from_date, until_date):
                date_str = str(day_date)
                column = MonthlyResourceAvailabilityDayColumn(accessor=A('days.%s' % date_str), orderable=False)
                extra_columns.append([day_date.strftime('%a, %d %b'), column])
        kwargs['extra_columns'] = extra_columns
        kwargs['sequence'] = ('user', '...')
        super().__init__(*args, **kwargs)


class ExpiringConsultancyContractOverviewTable(BaseTable):
    """Expiring consultancy contract overview table."""

    class Meta(BaseTable.Meta):
        # Hack, normally methods should have self as the first parameters. This is fine.
        # noinspection PyMethodParameters
        def determine_row_color(record):
            ends_at = record['calculated_enddate']
            if not ends_at:
                return
            if ends_at < date.today() + timedelta(days=30):
                return 'table-danger'  # Expires within 30 days
            if ends_at < date.today() + timedelta(days=60):
                return 'table-warning'  # Expires within 60 days
            if ends_at < date.today() + timedelta(days=90):
                return 'table-info'  # Expires within 90 days
            return

        row_attrs = {
            'class': determine_row_color
        }

    MULTIUSER_TEMPLATE = """
<ul style="margin:0;padding-inline-start:10px">
{% for user in value %}
    <li><a href="{% url 'admin:auth_user_change' user.id %}">{{ user }}</a></li>
{% empty %}
-
{% endfor %}
</ul>
    """

    contract = tables.LinkColumn(
        viewname='admin:ninetofiver_contract_change',
        args=[A('contract.id')],
        accessor='contract',
        order_by=['contract.name']
    )
    users = tables.TemplateColumn(
        template_code=MULTIUSER_TEMPLATE,
        accessor='users',
    )

    status = tables.Column(accessor='contract_log')
    day_rate = EuroColumn(accessor='contract.day_rate')
    starts_at = tables.DateColumn('d/m/Y', accessor='contract.starts_at')
    ends_at = tables.DateColumn('d/m/Y', accessor='contract.ends_at')
    alotted_hours = SummedHoursColumn(accessor='alotted_hours')
    performed_hours = SummedHoursColumn(accessor='performed_hours')
    remaining_hours = SummedHoursColumn(accessor='remaining_hours')
    calculated_enddate = tables.Column()
    actions = tables.Column(accessor='contract', orderable=False, exclude_from_export=True)

    def render_calculated_enddate(self, record):
        # A hack to fix the sorting
        # We want contracts without enddate to end up at the end, equal to enddate if the far future.
        # When populating the table date (in views.py) we transform contracts without enddate to an enddate of 31/12/2999
        # In this function we transform them back to '—'
        if record['calculated_enddate'] == date(2999, 12, 31):
            return format_html('—')
        else:
            return format_html(record['calculated_enddate'].strftime('%d/%m/%Y'))

    def render_actions(self, record):
        buttons = []

        buttons.append(('<a class="button" href="%(url)s?' +
                        'performance__contract=%(contract)s">Performances</a>') % {
            'url': reverse('admin_report_timesheet_contract_overview'),
            'contract': record['contract'].id,
        })

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class InvoicedConsultancyContractOverviewTable(BaseTable):

    class Meta(BaseTable.Meta):
        pass

    MULTIUSER_TEMPLATE = """
<ul style="margin:0;padding-inline-start:10px">
{% for user in value %}
    <li><a href="{% url 'admin:auth_user_change' user.id %}">{{ user }}</a></li>
{% empty %}
-
{% endfor %}
</ul>
    """

    contract = tables.LinkColumn(
        viewname='admin:ninetofiver_contract_change',
        args=[A('contract.id')],
        accessor='contract',
        order_by=['contract.name']
    )
    users = tables.TemplateColumn(
        template_code=MULTIUSER_TEMPLATE,
        accessor='users',
    )
    performed_hours = SummedHoursColumn(accessor='performed_hours')
    day_rate = EuroColumn(accessor='day_rate')
    to_be_invoiced = SummedEuroColumn(accessor='to_be_invoiced')
    invoiced = SummedInvoiceColoredEuroColumn(
        post_template_code='{% if record.invoiced_missing %} <span style="color:#f02311;font-weight:bold;" title="%s">(!)&nbsp;</span>{% endif %}',
        accessor='invoiced',
    )
    # missing = tables.Column(accessor='invoiced_missing', orderable=False, exclude_from_export=True)
    # performed_invoiced = SummedHoursColumn(accessor='performed_invoiced')
    actions = tables.Column(accessor='contract', orderable=False, exclude_from_export=True)

    def render_actions(self, record):
        buttons = []

        buttons.append(('<a class="button" href="%(url)s?' +
                        'performance__contract=%(contract)s&' +
                        'sort=-timesheet' +
                        '">Performances</a>') % {
            'url': reverse('admin_report_timesheet_contract_overview'),
            'contract': record['contract'].id,
        })

        buttons.append('<a class="button" style="border-top-right-radius: 0px; border-bottom-right-radius: 0px; padding-right: 0px;" href="{url}?'
                       'contract__id__exact={contract_id}'
                       '">Invoices</a>'.format(
                           url=reverse('admin:ninetofiver_invoice_changelist'),
                           contract_id=record['contract'].id)
                       +
                       '<a class="button" style="border-top-left-radius: 0px; border-bottom-left-radius: 0px;"href="{url}?'
                       'contract={contract_id}&'
                       'period_starts_at={period_starts_at}&'
                       'period_ends_at={period_ends_at}&'
                       'date={date}&'
                       'price={price}&'
                       'amount={amount}&'
                       '">{label}</a>'.format(url=reverse('admin:ninetofiver_invoice_add'),
                                              label="+",
                                              contract_id=record['contract'].id,
                                              period_starts_at=record['action'].get('period_starts_at'),
                                              period_ends_at=record['action'].get('period_ends_at'),
                                              date=record['action'].get('date'),
                                              price=record['action'].get('price'),
                                              amount=record['action'].get('amount'),
                                              ))

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class ProjectContractOverviewTable(BaseTable):
    """Project contract overview table."""

    export_formats = []

    class Meta(BaseTable.Meta):
        pass

    contract = tables.Column(accessor='contract', orderable=True,
                             order_by=['contract.customer.name', 'contract.name'],
                             attrs={
                                 'th': {
                                     'style': 'width: 15%; min-width: 150px;'
                                 }
                             })
    data = tables.TemplateColumn(template_name='ninetofiver/admin/reports/project_data.pug',
                                 accessor='', orderable=False)

    # actions = tables.Column(accessor='user', orderable=False, exclude_from_export=True)

    def render_contract(self, record):
        buttons = []

        buttons.append(('<a href="%(url)s' +
                        '%(contract_id)s">%(contract)s</a>') % {
            'url': reverse('admin:ninetofiver_contract_changelist'),
            'contract_id': record['contract'].id,
            'contract': record['contract'],
        })

        buttons.append(('<a class="button" href="%(url)s?' +
                        'performance__contract=%(contract)s">Performances</a>') % {
            'url': reverse('admin_report_timesheet_contract_overview'),
            'contract': record['contract'].id,
        })

        buttons.append('<a class="button" style="border-top-right-radius: 0px; border-bottom-right-radius: 0px; padding-right: 0px;" href="{url}?'
                       'contract__id__exact={contract_id}'
                       '">Invoices</a>'.format(
                           url=reverse('admin:ninetofiver_invoice_changelist'),
                           contract_id=record['contract'].id)
                       +
                       '<a class="button" style="border-top-left-radius: 0px; border-bottom-left-radius: 0px;" href="{url}?'
                       'contract={contract_id}&'
                       '">{label}</a>'.format(url=reverse('admin:ninetofiver_invoice_add'),
                                              label="+",
                                              contract_id=record['contract'].id)
                       )
        buttons.append(('<a class="button" target="_blank" href="%(url)s?' +
                        'contract=%(contract)s">Logs</a>') % {
            'url': reverse('admin_report_contract_logs_overview_view'),
            'contract': record['contract'].id,
        })

        attachment_list = ""
        for attachment in record['attachments']:
            attachment_list = attachment_list + \
                '<a class="dropdown-item" href="{url}">{name}</a>'.format(
                    url=record['attachments'][attachment]['url'], name=attachment)
        if attachment_list:
            buttons.append('<div class="dropdown">'
                           '<a class="button dropdown-toggle" href="#" type="button" id="dropdownMenuLink" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">Attachments</a>'
                           '<div class="dropdown-menu" aria-labelledby="dropdownMenuLink">' +
                           attachment_list +
                           '</div></div>')
        else:
            buttons.append('<div class="dropdown">'
                           '<a disabled class="button dropdown-toggle" type="button" id="dropdownMenuLink" data-toggle="dropdown" aria-disabled="true" aria-haspopup="true" aria-expanded="false">Attachments</a>'
                           '</div>')

        return format_html('%s' % ('</br></br>'.join(buttons)))

    def render_actions(self, record):
        buttons = []

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class UserOvertimeOverviewTable(BaseTable):
    """User overtime overview table."""

    class Meta(BaseTable.Meta):
        pass

    year = tables.Column()
    month = tables.Column()
    remaining_hours = HoursColumn()
    overtime_hours = SummedHoursColumn()
    used_overtime_hours = SummedHoursColumn()
    remaining_overtime_hours = HoursColumn()
    actions = tables.Column(accessor='user', orderable=False, exclude_from_export=True)

    def render_actions(self, record):
        buttons = []

        date_range = month_date_range(record['year'], record['month'])

        buttons.append(('<a class="button" href="%(url)s?' +
                        'user=%(user)s&' +
                        'from_date=%(from_date)s&' +
                        'until_date=%(until_date)s">Details</a>') % {
            'url': reverse('admin_report_user_range_info'),
            'user': record['user'].id,
            'from_date': date_range[0].strftime('%Y-%m-%d'),
            'until_date': date_range[1].strftime('%Y-%m-%d'),
        })

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class ExpiringSupportContractOverviewTable(BaseTable):
    """Expiring support contract overview table."""

    class Meta(BaseTable.Meta):
        pass

    contract = tables.LinkColumn(
        viewname='admin:ninetofiver_contract_change',
        args=[A('contract.id')],
        accessor='contract',
        order_by=['contract.customer.name', 'contract.name']
    )
    starts_at = tables.DateColumn('d/m/Y', accessor='contract.starts_at')
    ends_at = tables.DateColumn('d/m/Y', accessor='contract.ends_at')
    day_rate = tables.Column(accessor='contract.day_rate')
    fixed_fee = tables.Column(accessor='contract.fixed_fee')
    fixed_fee_period = tables.Column(accessor='contract.fixed_fee_period')
    last_invoiced_periode = tables.DateColumn('d/m/Y', accessor='last_invoiced_period')
    actions = tables.Column(accessor='contract', orderable=False, exclude_from_export=True)

    def render_actions(self, record):
        buttons = []

        buttons.append(('<a class="button" href="%(url)s?' +
                        'performance__contract=%(contract)s">Performances</a>') % {
            'url': reverse('admin_report_timesheet_contract_overview'),
            'contract': record['contract'].id,
        })

        buttons.append('<a class="button" style="border-top-right-radius: 0px; border-bottom-right-radius: 0px; padding-right: 0px;" href="{url}?'
                       'contract__id__exact={contract_id}'
                       '">Invoices</a>'.format(
                           url=reverse('admin:ninetofiver_invoice_changelist'),
                           contract_id=record['contract'].id)
                       +
                       '<a class="button" style="border-top-left-radius: 0px; border-bottom-left-radius: 0px;" href="{url}?'
                       'contract={contract_id}&'
                       '">{label}</a>'.format(url=reverse('admin:ninetofiver_invoice_add'),
                                              label="+",
                                              contract_id=record['contract'].id)
                       )

        return format_html('%s' % ('&nbsp;'.join(buttons)))


class ProjectContractBudgetOverviewTable(BaseTable):
    """Project contract budget overview table."""

    export_formats = []

    class Meta(BaseTable.Meta):
        pass

    contract = tables.LinkColumn(
        viewname="admin:ninetofiver_contract_change",
        args=[A("contract.id")],
        accessor="contract",
        order_by=["contract.name"],
        attrs={"th": {"style": "width: 15%; min-width: 150px;"}},
    )
    invoiced = tables.TemplateColumn(
        template_name="ninetofiver/admin/reports/project_budget_invoiced.pug",
        accessor="",
        order_by=["-invoiced_pct"],
    )
    performed = tables.TemplateColumn(
        template_name="ninetofiver/admin/reports/project_budget_performed.pug",
        accessor="",
        order_by=["-estimated_pct"],
    )
    last_change = tables.DateColumn(
        "d/m/Y",
        accessor="contract.last_performance.date",
        order_by=["contract.last_performance.date"]
    )
    # actions = tables.Column(accessor='contract', orderable=False, exclude_from_export=True)

    def render_contract(self, record):
        buttons = []

        buttons.append(
            ('<a href="%(url)s' + '%(contract_id)s">%(contract)s</a><br><br>')
            % {
                "url": reverse("admin:ninetofiver_contract_changelist"),
                "contract_id": record["contract"].id,
                "contract": record["contract"],
            }
        )
        buttons.append(
            (
                '<a class="button" href="%(url)s?'
                + 'contract_ptr=%(contract)s">Details</a>'
            )
            % {
                "url": reverse("admin_report_project_contract_overview"),
                "contract": record["contract"].id,
            }
        )

        return format_html("%s" % ("&nbsp;".join(buttons)))


class ExpiringUserTrainingOverviewTable(BaseTable):
    """Expiring support contract overview table."""

    class Meta(BaseTable.Meta):
        pass

    user = tables.LinkColumn(
        viewname='admin:auth_user_change',
        args=[A('training.user_training.user.id')],
        accessor='training.user_training.user',
        order_by=['training.user_training.user.first_name',
                  'training.user_training.user.last_name', 'training.user_training.user.username']
    )

    training_type = tables.Column(
        accessor='training.training_type'
    )
    training_description = tables.Column(
        accessor='training.training_type.description'
    )

    mandatory = tables.BooleanColumn(accessor='training.training_type.mandatory')
    starts_at = tables.DateColumn('d/m/Y', accessor='training.starts_at')
    ends_at = tables.DateColumn('d/m/Y', accessor='training.ends_at')
    remaining_days = tables.Column(accessor='training.remaining_days')
    required_action = tables.Column(accessor='training.training_type.required_action')

    actions = tables.Column(accessor='training', orderable=False, exclude_from_export=True)

    def render_actions(self, record):
        buttons = []

        buttons.append('<a class="button" href="{url}?">{label}</a>'.format(
            url=reverse('admin:ninetofiver_usertraining_change', args=(record['training'].user_training.id,)),
            label="Details"
        ))

        return format_html('%s' % ('&nbsp;'.join(buttons)))

class ContractLogOverviewTable(BaseTable):
    """Timesheet contract overview table."""

    class Meta(BaseTable.Meta):
        pass

    contract = tables.LinkColumn(
        viewname="admin:ninetofiver_contract_change",
        args=[A("contract.id")],
        order_by=["contract.name"],
    )
    date = tables.Column()
    log = tables.Column()
    log_type = tables.Column()