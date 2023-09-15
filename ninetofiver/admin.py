"""Admin."""
import logging
from datetime import date

from django.conf import settings
from admin_auto_filters.filters import AutocompleteFilterFactory
from adminsortable.admin import SortableAdmin
from django import forms
from django.contrib import admin, messages
from django.contrib.admin import widgets
from django.contrib.auth import models as auth_models
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q, Prefetch, TextField, Min
from django.forms import TextInput
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django_admin_listfilter_dropdown.filters import DropdownFilter
from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter
from django_countries.filters import CountryFilter
from import_export import fields
from import_export.admin import ExportMixin
from import_export.fields import Field
from import_export.resources import ModelResource
from polymorphic.admin import PolymorphicChildModelAdmin
from polymorphic.admin import PolymorphicChildModelFilter
from polymorphic.admin import PolymorphicParentModelAdmin
from rangefilter.filter import DateRangeFilter
from rangefilter.filter import DateTimeRangeFilter
from django.shortcuts import render
from django_select2 import forms as select2_widgets
from django.utils.safestring import mark_safe

from ninetofiver import models, redmine
from ninetofiver.filters import CompanyFilter
from ninetofiver.models import Timesheet, Contract
from ninetofiver.templatetags.markdown import markdown
from ninetofiver.utils import IntelligentManyToManyWidget

from .forms import PerformanceContractForm

log = logging.getLogger(__name__)

# Enable old-style admin view
admin.site.enable_nav_sidebar = False


class GroupForm(forms.ModelForm):
    """Group form."""

    users = forms.ModelMultipleChoiceField(
        label=_('Users'),
        required=False,
        queryset=auth_models.User.objects.all(),
        widget=admin.widgets.FilteredSelectMultiple('users', is_stacked=False)
    )

    class Meta:
        model = auth_models.Group
        fields = '__all__'
        widgets = {
            'permissions': admin.widgets.FilteredSelectMultiple(verbose_name="Permissions", is_stacked=False),
        }


class GroupAdmin(BaseGroupAdmin):
    """Group admin."""

    form = GroupForm

    def save_model(self, request, obj, form, change):
        """Save the given model."""
        super(GroupAdmin, self).save_model(request, obj, form, change)
        obj.user_set.set(form.cleaned_data['users'])

    def get_form(self, request, obj=None, **kwargs):
        """Get the form."""
        pks = [x.pk for x in obj.user_set.all()] if obj else []
        self.form.base_fields['users'].initial = pks

        return GroupForm


# Unregister previous admin to register current one
admin.site.unregister(auth_models.Group)
admin.site.register(auth_models.Group, GroupAdmin)


@admin.register(models.ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    """Api key admin."""

    list_display = ('__str__', 'name', 'key', 'read_only', 'user', 'created_at')
    ordering = ('-created_at',)


class EmploymentContractStatusFilter(admin.SimpleListFilter):
    """Employment contract status filter."""

    title = 'Status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return (
            ('active', _('Active')),
            ('ended', _('Ended')),
            ('future', _('Future')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(
                Q(started_at__lte=date.today()) &
                (Q(ended_at__gte=date.today()) | Q(ended_at__isnull=True))
            )
        elif self.value() == 'ended':
            return queryset.filter(ended_at__lte=date.today())
        elif self.value() == 'future':
            return queryset.filter(started_at__gte=date.today())


class ContractStatusFilter(admin.SimpleListFilter):
    """Contract status filter."""

    title = 'Status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return (
            ('active', _('Active')),
            ('ended', _('Ended')),
            ('future', _('Future')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(
                Q(starts_at__lte=date.today()) &
                (Q(ends_at__gte=date.today()) | Q(ends_at__isnull=True)) &
                Q(active=True)
            )
        elif self.value() == 'ended':
            return queryset.filter(Q(ends_at__lte=date.today()) | Q(active=False))
        elif self.value() == 'future':
            return queryset.filter(starts_at__gte=date.today())


@admin.register(models.Company)
class CompanyAdmin(admin.ModelAdmin):
    """Company admin."""

    def logo(obj):
        return format_html('<a href="%s">%s</a>' % (obj.get_logo_url(), _('Link')))

    list_display = ('__str__', 'name', 'vat_identification_number', 'address', 'country', 'internal', logo)
    ordering = ('-internal', 'name')
    # NOTE (to my future self): see similar note in ninetofiver/filters.py
    search_fields = ('name',)


@admin.register(models.EmploymentContractType)
class EmploymentContractTypeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'name')
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(models.EmploymentContract)
class EmploymentContractAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'employment_contract_type', 'work_schedule', 'started_at', 'ended_at')
    list_filter = (
        EmploymentContractStatusFilter,
        AutocompleteFilterFactory('User', 'user'),
        AutocompleteFilterFactory('Company', 'company'),
        AutocompleteFilterFactory('Employment Contract Type', 'employment_contract_type'),
        ('started_at', DateRangeFilter),
        ('ended_at', DateRangeFilter)
    )
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'employment_contract_type__name',
                     'started_at', 'ended_at')
    ordering = ('user__first_name', 'user__last_name')
    autocomplete_fields = ('user', 'company', 'employment_contract_type',)


@admin.register(models.WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'name', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
    ordering = ('name',)


@admin.register(models.UserRelative)
class UserRelativeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'name', 'user', 'relation', 'gender', 'birth_date',)
    ordering = ('name',)
    autocomplete_fields = ('user',)


class AttachmentAdminForm(forms.ModelForm):
    model = models.Attachment
    def clean(self):
        t = self.cleaned_data.get("type")
        if t == "c" and not self.request.user.has_perm("ninetofiver.change_contract"):
            raise forms.ValidationError("You are not allowed to create contract attachments")
        elif t == "l" and not self.request.user.has_perm("ninetofiver.change_leave"):
            raise forms.ValidationError("You are not allowed to create leave attachments")
        return self.cleaned_data

@admin.register(models.Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    form = AttachmentAdminForm
    
    def get_form(self, request, *args, **kwargs):
        form = super(AttachmentAdmin, self).get_form(request, *args, **kwargs)
        form.request = request
        return form
    
    def link(self, obj):
        return format_html('<a href="%s">%s</a>' % (obj.get_file_url(), str(obj)))

    def get_queryset(self, request):
        qs = super(AttachmentAdmin, self).get_queryset(request)
        if not request.user.has_perm("ninetofiver.change_leave"):
            qs = qs.exclude(type="l")
        if not request.user.has_perm("ninetofiver.change_contract"):
            qs = qs.exclude(type="c")
        return qs

    list_display = ('__str__', 'user', 'name', 'description', 'file', 'slug', 'link', 'type')
    list_filter = ["type"]
    readonly_fields=('type',)


@admin.register(models.Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'name', 'date', 'country')
    ordering = ('-date',)
    list_filter = (
        ('country', DropdownFilter),
        ('date', DateRangeFilter)
    )
    search_fields = ('name',)


@admin.register(models.LeaveType)
class LeaveTypeAdmin(SortableAdmin):
    """Leave type admin."""

    list_display = ('__str__', 'name', 'description', 'overtime', 'sickness')


class LeaveDateInline(admin.TabularInline):
    """Leave date inline."""

    model = models.LeaveDate

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == "timesheet" and hasattr(self, 'cached_timesheets'):
            # use cached options because django will fetch them multiple times otherwise
            formfield.choices = self.cached_timesheets

        return formfield

class LeaveAdminForm(forms.ModelForm):
    model = models.Leave
    
    def clean(self):
        if self.cleaned_data.get('attachments') is not None:
            for att in self.cleaned_data.get('attachments'):
                if att.type == "c":
                    raise forms.ValidationError("You cannot add a non-leave attachment to a leave!")
        return self.cleaned_data

@admin.register(models.Leave)
class LeaveAdmin(admin.ModelAdmin):
    """Leave admin."""
    change_form_template = "ninetofiver/admin/leave_changeform.html"
    form = LeaveAdminForm
    
    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('leave_type', 'user')
            .prefetch_related('attachments')
            .annotate(_first_day=Min("leavedate__starts_at"))
            .order_by('_first_day')
        )

    def get_formsets_with_inlines(self, request, obj=None):
        """Cache timesheets foreign-keys in inlines"""
        cached_timesheets = [(None, "---------")]
        if obj:
            cached_timesheets.extend([(i.pk, str(i)) for i in Timesheet.objects.filter(user=obj.user)])
        else:
            cached_timesheets.extend([(i.pk, str(i)) for i in Timesheet.objects.all()])

        # populate all inlines with cached properties - probably should select th
        for inline in self.get_inline_instances(request, obj):
            inline.cached_timesheets = cached_timesheets
            yield inline.get_formset(request, obj), inline

    def make_approved(self, request, queryset):
        """Approve selected leaves."""
        for leave in queryset:
            leave.status = models.STATUS_APPROVED
            leave.save(validate=False)

    make_approved.short_description = _('Approve selected leaves')

    def make_rejected(self, request, queryset):
        """Reject selected leaves."""
        for leave in queryset:
            leave.status = models.STATUS_REJECTED
            leave.save(validate=False)

    make_rejected.short_description = _('Reject selected leaves')

    def date(self, obj):
        """List leave dates."""
        return format_html('<br>'.join(x.html_label() for x in list(obj.leavedate_set.all())))

    date.admin_order_field = "_first_day"

    def attachment(self, obj):
        """Attachment URLs."""
        return format_html('<br>'.join('<a href="%s">%s</a>'
                                       % (x.get_file_url(), str(x)) for x in list(obj.attachments.all())))


    def company(self, obj):
        """Company under which is user employed. If he is employed under more than one,
        then the first one is shown in related column, but in filters, all his/her companies are used."""
        company = models.Leave.objects.raw(f"""
          SELECT DISTINCT 1 as id, ninetofiver_company.name as company
from (((ninetofiver_leave INNER JOIN auth_user ON ninetofiver_leave.user_id = auth_user.id)
INNER JOIN ninetofiver_employmentcontract ON ninetofiver_employmentcontract.user_id = auth_user.id)
INNER JOIN ninetofiver_company on ninetofiver_employmentcontract.company_id = ninetofiver_company.id)
WHERE ninetofiver_leave.user_id = {obj.user_id};
                """)
        company = "None" if len(company) == 0 else company[0].company
        return company

    def item_actions(self, obj):
        """Actions."""
        actions = []

        if obj.status == models.STATUS_PENDING:
            actions.append('<a class="button" href="%s?return=true">%s</a>' %
                           (reverse('admin_leave_approve', kwargs={'leave_pk': obj.id}), _('Approve')))
            actions.append('<a class="button" href="%s?return=true">%s</a>' %
                           (reverse('admin_leave_reject', kwargs={'leave_pk': obj.id}), _('Reject')))

        return format_html('&nbsp;'.join(actions))

    list_display = (
        '__str__',
        'user',
        'leave_type',
        'date',
        'created_at',
        'status',
        'description',
        'attachment',
        'item_actions',
        'company',
    )
    list_filter = (
        'status',
        ('leave_type', RelatedDropdownFilter),
        AutocompleteFilterFactory('User', 'user'),
        CompanyFilter,
        ('user__groups', RelatedDropdownFilter),
        ('leavedate__starts_at', DateTimeRangeFilter),
        ('leavedate__ends_at', DateTimeRangeFilter)
    )
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'leave_type__name', 'status',
                     'leavedate__starts_at', 'leavedate__ends_at', 'description',)
    inlines = [
        LeaveDateInline,
    ]
    actions = [
        'make_approved',
        'make_rejected',
    ]
    ordering = ('-status',)
    autocomplete_fields = ('user',)
    filter_horizontal = ('attachments',)
    raw_id_fields = ("attachments",)


@admin.register(models.LeaveDate)
class LeaveDateAdmin(admin.ModelAdmin):

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Form field for foreign key."""
        if db_field.name == 'user':
            kwargs['queryset'] = auth_models.User.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    list_display = ('__str__', 'leave', 'starts_at', 'ends_at')
    ordering = ('-starts_at',)
    raw_id_fields = ('leave', 'timesheet')
    autocomplete_fields = ('timesheet',)


class UserInfoForm(forms.ModelForm):
    """User info form."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        super().__init__(*args, **kwargs)
        
        if "redmine_id" in self.fields:
            self.fields['redmine_id'].label = 'Redmine user'
            redmine_user_choices = cache.get_or_set('user_info_admin_redmine_id_choices',
                                                    redmine.get_redmine_user_choices)
            self.fields['redmine_id'].widget = forms.Select(choices=redmine_user_choices)


@admin.register(models.UserInfo)
class UserInfoAdmin(admin.ModelAdmin):
    def join_date(self, obj):
        return obj.get_join_date()

    def user_groups(self, obj):
        return format_html('<br>'.join(str(x) for x in list(obj.user.groups.all())))

    list_display = ('__str__', 'user', 'gender', 'birth_date', 'user_groups', 'country', 'join_date')
    list_filter = ('gender', 'user__groups', ('country', CountryFilter))
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name',)
    ordering = ('user',)
    autocomplete_fields = ('user',)
    form = UserInfoForm


@admin.register(models.PerformanceType)
class PerformanceTypeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'name', 'description', 'multiplier')


@admin.register(models.ContractGroup)
class ContractGroupAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'name',)
    search_fields = ('name',)


@admin.register(models.ContractLogType)
class ContractLogTypeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'name')
    search_fields = ('name',)
    ordering = ('name',)


class ContractUserInline(admin.TabularInline):
    model = models.ContractUser
    # Due to loading improvements, also user is raw_id_field
    # autocomplete_fields = ['user']
    # ordering = ("user__first_name", "user__last_name",)
    show_change_link = True
    raw_id_fields = ('user', 'contract_role',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Form field for foreign key."""
        if db_field.name == 'user':
            kwargs['queryset'] = auth_models.User.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .select_related('user', 'contract_role')
                )


class ContractUserGroupInline(admin.TabularInline):
    model = models.ContractUserGroup


class ContractEstimateInline(admin.TabularInline):
    model = models.ContractEstimate


class ContractLogInline(admin.TabularInline):
    view_on_site = False
    model = models.ContractLog
    formfield_overrides = {
        TextField: {'widget': TextInput(attrs={'size': '60'})},
    }


class ContractForm(forms.ModelForm):
    """Contract form."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        super().__init__(*args, **kwargs)
        
        if "redmine_id" in self.fields:
            self.fields['redmine_id'].label = 'Redmine project'
            redmine_project_choices = cache.get_or_set('contract_admin_redmine_id_choices',
                                                    redmine.get_redmine_project_choices)
            self.fields['redmine_id'].widget = select2_widgets.Select2Widget(choices=redmine_project_choices)
    
    def clean(self):
        if self.cleaned_data.get('attachments') is not None:
            for att in self.cleaned_data.get('attachments'):
                log.info(att.type)
                if att.type == "l":
                    raise forms.ValidationError("You cannot add a non-contract attachment to a contract!")
        return self.cleaned_data

class ContractResource(ModelResource):
    """Contract resource."""

    contract_users = fields.Field(
        column_name='users',
        attribute='contract_users',
        widget=IntelligentManyToManyWidget(User, lookup='get_full_name'))

    class Meta:
        """Contract resource meta class."""

        model = models.Contract
        fields = (
            'id',
            'name',
            'company__id',
            'company__name',
            'customer__id',
            'customer__name',
            'active',
            'starts_at',
            'ends_at',
            'description',
            'projectcontract__fixed_fee',
            'consultancycontract__duration',
            'consultancycontract__day_rate',
            'supportcontract__fixed_fee',
            'supportcontract__fixed_fee_period',
            'supportcontract__day_rate',
            'polymorphic_ctype__model',
        )
        export_order = (
            'id',
            'name',
            'description',
            'starts_at',
            'ends_at',
            'active',
            'company__id',
            'company__name',
            'customer__id',
            'customer__name',
            'contract_users',
            'projectcontract__fixed_fee',
            'consultancycontract__duration',
            'consultancycontract__day_rate',
            'supportcontract__fixed_fee',
            'supportcontract__fixed_fee_period',
            'supportcontract__day_rate',
            'polymorphic_ctype__model',
        )


@admin.register(models.Contract)
class ContractParentAdmin(ExportMixin, PolymorphicParentModelAdmin):
    """Contract parent admin."""

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .select_related('company', 'customer')
                .prefetch_related('contractusergroup_set',
                                  'contractusergroup_set__group', 'contractusergroup_set__contract_role',
                                  'contractuser_set', 'contractuser_set__user',
                                  'contractuser_set__contract_role',
                                  Prefetch('performance_types', queryset=(models.PerformanceType.objects
                                                                          .non_polymorphic())),
                                  Prefetch('attachments', queryset=(models.Attachment.objects
                                                                    .non_polymorphic()))))

    def contract_users(obj):
        return format_html('<br>'.join(str(x) for x in list(obj.contractuser_set.all())))

    def contract_user_groups(obj):
        return format_html('<br>'.join(str(x) for x in list(obj.contractusergroup_set.all())))

    def performance_type(obj):
        return format_html('<br>'.join(str(x) for x in list(obj.performance_types.all())))

    def attachments(obj):
        return format_html('<br>'.join('<a href="%s">%s</a>'
                                       % (x.get_file_url(), str(x)) for x in list(obj.attachments.all())))

    def fixed_fee(obj):
        real_obj = obj.get_real_instance()
        if real_obj.__class__ in [models.ProjectContract, models.SupportContract]:
            return real_obj.fixed_fee
        return None

    def fixed_fee_period(obj):
        real_obj = obj.get_real_instance()
        if real_obj.__class__ is models.SupportContract:
            return real_obj.fixed_fee_period
        return None

    def duration(obj):
        real_obj = obj.get_real_instance()
        if real_obj.__class__ is models.ConsultancyContract:
            return real_obj.duration
        return None

    def day_rate(obj):
        real_obj = obj.get_real_instance()
        if real_obj.__class__ in [models.ConsultancyContract, models.SupportContract]:
            return real_obj.day_rate
        return None

    def item_actions(obj):
        """Actions."""
        actions = []

        actions.append('<a class="button" href="%s?contract__id__exact=%s">%s</a>' %
                       (reverse('admin:ninetofiver_invoice_changelist'), obj.id, _('Invoices')))

        return format_html('&nbsp;'.join(actions))

    resource_class = ContractResource
    polymorphic_list = True

    base_model = models.Contract
    child_models = (
        models.ProjectContract,
        models.ConsultancyContract,
        models.SupportContract,
    )
    list_display = ('__str__', 'name', 'company', 'customer', contract_users, contract_user_groups, performance_type,
                    'active', 'starts_at', 'ends_at', 'description', attachments, fixed_fee, fixed_fee_period,
                    duration, day_rate, item_actions)

    list_filter = (
        PolymorphicChildModelFilter,
        ContractStatusFilter,
        AutocompleteFilterFactory('company', 'company'),
        AutocompleteFilterFactory('customer', 'customer'),
        AutocompleteFilterFactory('contract groups', 'contract_groups'),
        AutocompleteFilterFactory('user', 'contractuser__user'),
        ('contractusergroup__group', RelatedDropdownFilter),
        ('performance_types', RelatedDropdownFilter),
        ('starts_at', DateRangeFilter),
        ('ends_at', DateRangeFilter),
        'active'
    )
    search_fields = ('id', 'name', 'description', 'company__name', 'customer__name', 'contractuser__user__first_name',
                     'contractuser__user__last_name', 'contractuser__user__username', 'contractusergroup__group__name',
                     'performance_types__name')
    ordering = ('name', 'company', 'starts_at', 'ends_at', '-customer',)
    autocomplete_fields = ('company', 'customer')


class ContractChildAdmin(PolymorphicChildModelAdmin):
    """Base contract admin."""

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .select_related('company', 'customer')
                .prefetch_related('contractusergroup_set',
                                  'contractusergroup_set__group', 'contractusergroup_set__contract_role',
                                  'contractuser_set', 'contractuser_set__user',
                                  'contractuser_set__contract_role',
                                  'attachments', 'performance_types',
                                  ).distinct())

    inlines = [
        ContractLogInline,
        ContractEstimateInline,
        ContractUserGroupInline,
        ContractUserInline,
    ]
    base_model = models.Contract
    base_form = ContractForm
    list_display = ContractParentAdmin.list_display
    list_filter = ContractParentAdmin.list_filter[1:]
    search_fields = ContractParentAdmin.search_fields
    ordering = ContractParentAdmin.ordering
    filter_horizontal = ('attachments', "contract_groups", "performance_types", )
    raw_id_fields = ("attachments",)


@admin.register(models.ConsultancyContract)
class ConsultancyContractAdmin(ContractChildAdmin):
    """Consultancy contract admin."""

    base_model = models.ConsultancyContract
    autocomplete_fields = ('company', 'customer')


@admin.register(models.SupportContract)
class SupportContractAdmin(ContractChildAdmin):
    """Support contract admin."""

    base_model = models.SupportContract
    autocomplete_fields = ('company', 'customer')


@admin.register(models.ProjectContract)
class ProjectContractAdmin(ContractChildAdmin):
    """Project contract admin."""

    base_model = models.ProjectContract
    autocomplete_fields = ('company', 'customer')


@admin.register(models.ContractRole)
class ContractRoleAdmin(admin.ModelAdmin):
    """Contract role admin."""
    list_display = ('__str__', 'name', 'description')
    ordering = ('name',)
    search_fields = ('name',)


class ContractUserWorkScheduleInline(admin.TabularInline):
    model = models.ContractUserWorkSchedule


@admin.register(models.ContractUser)
class ContractUserAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'contract', 'contract_role')
    ordering = ('user__first_name', 'user__last_name')
    inlines = [
        ContractUserWorkScheduleInline,
    ]
    list_filter = (
        AutocompleteFilterFactory('Contract', 'contract'),
        AutocompleteFilterFactory('User', 'user'),
        AutocompleteFilterFactory('Contract role', 'contract_role'),
    )
    raw_id_fields = ('contract',)
    autocomplete_fields = ('user', 'contract_role',)


@admin.register(models.Timesheet)
class TimesheetAdmin(admin.ModelAdmin):
    """Timesheet admin."""

    def get_queryset(self, request):
        """Get the queryset."""
        return super().get_queryset(request).select_related('user').prefetch_related('attachments')

    def attachments(obj):
        return format_html('<br>'.join('<a href="%s">%s</a>'
                                       % (x.get_file_url(), str(x)) for x in list(obj.attachments.all())))

    def make_closed(self, request, queryset):
        for timesheet in queryset:
            timesheet.status = models.STATUS_CLOSED
            timesheet.save(validate=False)

    make_closed.short_description = _('Close selected timesheets')

    def make_active(self, request, queryset):
        for timesheet in queryset:
            timesheet.status = models.STATUS_ACTIVE
            timesheet.save(validate=False)

    make_active.short_description = _('Activate selected timesheets')

    def make_pending(self, request, queryset):
        for timesheet in queryset:
            timesheet.status = models.STATUS_PENDING
            timesheet.save(validate=False)

    make_pending.short_description = _('Set selected timesheets to pending')

    def item_actions(self, obj):
        """Actions."""
        actions = []

        if obj.status == models.STATUS_PENDING:
            actions.append('<a class="button" href="%s?return=true">%s</a>' %
                           (reverse('admin_timesheet_close', kwargs={'timesheet_pk': obj.id}), _('Close')))
            actions.append('<a class="button" href="%s?return=true">%s</a>' %
                           (reverse('admin_timesheet_activate', kwargs={'timesheet_pk': obj.id}), _('Reopen')))

        return format_html('&nbsp;'.join(actions))

    list_display = ('__str__', 'user', 'month', 'year', 'status', attachments, 'item_actions')
    list_filter = (
        'status',
        AutocompleteFilterFactory('user', 'user'),
        'year',
        'month',
    )
    actions = [
        'make_closed',
        'make_active',
        'make_pending',
    ]
    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name',
        'status',
    )
    ordering = ('-year', 'month', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('user',)
    filter_horizontal= ('attachments',)
    raw_id_fields = ("attachments",)


@admin.register(models.Location)
class LocationAdmin(SortableAdmin):
    """Location admin."""

    list_display = (
        '__str__',
        'name',
    )
    search_fields = ('name',)


@admin.register(models.Whereabout)
class WhereaboutAdmin(admin.ModelAdmin):
    """Whereabout admin."""

    list_display = (
        '__str__',
        'timesheet',
        'location',
        'starts_at',
        'ends_at',
        'description',
    )
    list_filter = (
        ('location', RelatedDropdownFilter),
        AutocompleteFilterFactory('user', 'timesheet__user'),
        ('starts_at', DateTimeRangeFilter),
        ('ends_at', DateTimeRangeFilter)
    )
    search_fields = ('timesheet__user__username', 'timesheet__user__first_name', 'timesheet__user__last_name',
                     'location__name', 'starts_at', 'ends_at', 'description')
    ordering = ('-starts_at',)
    raw_id_fields = ('timesheet',)


class InuitsKrkPerformanceResource(ModelResource):
    """Performance resource."""
    date = Field(attribute='date', column_name='date')
    full_name = Field(attribute='timesheet__user__get_full_name', column_name='full_name')

    class Meta:
        """Performance resource meta class."""
        model = models.PerformanceInuitsKrk
        fields = (
            'date',
            'full_name',
            'timesheet__user__username',
            'timesheet__year',
            'timesheet__month',
            'timesheet__status',
            'activityperformance__duration',
            'activityperformance__description',
            'activityperformance__contract_role__id',
            'activityperformance__contract_role__name'
        )


class PerformanceResource(ModelResource):
    """Performance resource."""

    class Meta:
        """Performance resource meta class."""

        model = models.Performance
        fields = (
            'id',
            'timesheet__user__id',
            'timesheet__user__username',
            'timesheet__user__first_name',
            'timesheet__user__last_name',
            'timesheet__year',
            'timesheet__month',
            'timesheet__status',
            'date',
            'contract__id',
            'contract__name',
            'activityperformance__duration',
            'activityperformance__description',
            'activityperformance__performance_type__id',
            'activityperformance__performance_type__name',
            'activityperformance__contract_role__id',
            'activityperformance__contract_role__name',
            'polymorphic_ctype__model',
        )


class ContractListFilter(admin.SimpleListFilter):
    title = 'Contract'
    parameter_name = "contract"
    template = 'django_admin_listfilter_dropdown/dropdown_filter.html'

    def lookups(self, request, model_admin):
        query = models.Contract.objects.non_polymorphic().select_related('customer', 'company')
        return [(con.pk, str(con)) for con in query]

    def queryset(self, request, queryset):
        if self.value():
            try:
                value = int(self.value())
            except TypeError:
                value = None
                return queryset

            for choice_value, _ in self.lookup_choices:
                if choice_value == value:
                    return queryset.filter(contract=choice_value)
            return queryset.filter(contract=None)
        return queryset


@admin.register(models.Performance)
class PerformanceParentAdmin(ExportMixin, PolymorphicParentModelAdmin):
    """Performance parent admin."""

    resource_class = PerformanceResource
    polymorphic_list = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('contract',
                                                            'contract__customer',
                                                            'timesheet',
                                                            'timesheet__user')

    def duration(self, obj):
        return obj.activityperformance.duration

    def performance_type(self, obj):
        return obj.activityperformance.performance_type

    def a_description(self, obj):
        value = obj.activityperformance.description
        value = markdown(value) if value else value
        return value

    def contract_role(self, obj):
        return obj.activityperformance.contract_role
    
    @admin.action(description="Contract bulk change")
    def contract_bulk_change(self, request, queryset):
        if request.POST.get("do_action"):
            form = PerformanceContractForm(request.POST)
            if form.is_valid():
                return render(
                    request,
                    "admin/actions/action_bulk_contract_to_performance_confirm.html",
                    {
                        "title": "Confirm the change",
                        "contract": form.cleaned_data["contract"],
                        "objects": queryset,
                        "form": form,
                    },
                )
        elif request.POST.get("confirm"):
            form = PerformanceContractForm(request.POST)
            if form.is_valid():
                contract = form.cleaned_data["contract"]
                updated = queryset.update(contract=contract)
                messages.success(request, "{0} contracts were updated".format(updated))
                return
        else:
            form = PerformanceContractForm()
        return render(
            request,
            "admin/actions/action_bulk_contract_to_performance.html",
            {
                "title": "Choose contract",
                "objects": queryset,
                "form": form,
            },
        )


    base_model = models.Performance
    child_models = (
        models.ActivityPerformance,
        models.StandbyPerformance,
    )
    list_filter = (
        PolymorphicChildModelFilter,
        AutocompleteFilterFactory("contract", "contract"),
        AutocompleteFilterFactory('company', 'contract__company'),
        AutocompleteFilterFactory('customer', 'contract__customer'),
        AutocompleteFilterFactory('user', 'timesheet__user'),
        ('timesheet__year', DropdownFilter),
        ('timesheet__month', DropdownFilter),
        ('date', DateRangeFilter),
        AutocompleteFilterFactory('contract role', 'activityperformance__contract_role'),
        ('activityperformance__performance_type', RelatedDropdownFilter),
    )
    list_display = (
        '__str__',
        'timesheet',
        'date',
        'contract',
        'performance_type',
        'duration',
        'a_description',
        'contract_role',
    )
    actions = [
        'contract_bulk_change',
    ]


@admin.register(models.PerformanceInuitsKrk)
class PerformanceInuitsKrkParentAdmin(ExportMixin, PolymorphicParentModelAdmin):
    resource_class = InuitsKrkPerformanceResource
    polymorphic_list = True

    def get_queryset(self, request):
        return models.Performance.objects.select_related('contract',
                                                         'contract__customer',
                                                         'timesheet',
                                                         'timesheet__user')
    def link(self, obj):
        return mark_safe(f'<a href="{settings.BASE_URL}/admin/ninetofiver/performance/{obj.id}/change/">{obj}</a>')        
    link.allow_tags = True
    link.short_description = "Performance"
    
    def duration(self, obj):
        return obj.activityperformance.duration

    def performance_type(self, obj):
        return obj.activityperformance.performance_type

    def description(self, obj):
        value = obj.activityperformance.description
        value = markdown(value) if value else value
        return value

    def contract_role(self, obj):
        return obj.activityperformance.contract_role

    base_model = models.Performance
    child_models = (
        models.ActivityPerformance,
        models.StandbyPerformance,
    )
    list_filter = (
        PolymorphicChildModelFilter,
        AutocompleteFilterFactory("contract", "contract"),
        AutocompleteFilterFactory('company', 'contract__company'),
        AutocompleteFilterFactory('customer', 'contract__customer'),
        AutocompleteFilterFactory('user', 'timesheet__user'),
        ('timesheet__year', DropdownFilter),
        ('timesheet__month', DropdownFilter),
        ('date', DateRangeFilter),
        AutocompleteFilterFactory('contract role', 'activityperformance__contract_role'),
        ('activityperformance__performance_type', RelatedDropdownFilter),
    )
    list_display = (
        'link',
        'timesheet',
        'date',
        'contract',
        'performance_type',
        'duration',
        'description',
        'contract_role',
    )


class PerformanceChildAdmin(PolymorphicChildModelAdmin):
    base_model = models.Performance
    raw_id_fields = ('contract',)


@admin.register(models.ActivityPerformance)
class ActivityPerformanceChildAdmin(PerformanceChildAdmin):
    base_model = models.ActivityPerformance

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .prefetch_related('performance_type')
                )

    autocomplete_fields = ('timesheet', 'contract_role')


@admin.register(models.StandbyPerformance)
class StandbyPerformanceChildAdmin(PerformanceChildAdmin):
    base_model = models.StandbyPerformance


class InvoiceItemInline(admin.TabularInline):
    """Invoice item inline."""

    model = models.InvoiceItem
    extra = 1

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        # Is it get?
        if request.method == "GET" and (not obj or not obj.id):
            data = {}
            price = request.GET.get('price')
            if price:
                data['price'] = price
                formset.form.base_fields['price'].initial = price

            amount = request.GET.get('amount')
            if amount:
                data['amount'] = amount
                formset.form.base_fields['amount'].initial = amount

        return formset


@admin.register(models.Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """Invoice admin."""

    def get_queryset(self, request):
        """Get the queryset."""
        return (super().get_queryset(request)
                .select_related('contract', 'contract__customer')
                .prefetch_related('invoiceitem_set'))

    def amount(self, obj):
        """Amount."""
        return sum([x.price * x.amount for x in obj.invoiceitem_set.all()])

    list_display = (
        '__str__',
        'date',
        'amount',
        'contract',
        'reference',
        'period_starts_at',
        'period_ends_at',
        'description',
    )
    list_filter = (
        AutocompleteFilterFactory('Contract', 'contract'),
        AutocompleteFilterFactory('Company', 'contract__company'),
        AutocompleteFilterFactory('Customer', 'contract__customer'),
        ('date', DateTimeRangeFilter),
        ('period_starts_at', DateTimeRangeFilter),
        ('period_ends_at', DateTimeRangeFilter),
    )
    search_fields = ('contract__name', 'reference', 'contract__name', 'contract__customer__name', 'contract__company__name',
                     'description', 'date')
    inlines = [
        InvoiceItemInline,
    ]
    ordering = ('-reference',)
    autocomplete_fields = ('contract',)


@admin.register(models.TrainingType)
class UserTrainingTypeAdmin(admin.ModelAdmin):
    """User training types admin"""

    list_display = (
        '__str__',
        'description',
        'mandatory',
        'country',
    )

    list_filter = (
        'mandatory',
        ('country', DropdownFilter),
    )


class TrainingInline(admin.TabularInline):
    model = models.Training
    extra = 0
    fields = ('training_type', 'starts_at', 'ends_at', 'remaining_days')
    readonly_fields = ('remaining_days',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == "training_type" and hasattr(self, 'training_types_choices'):
            # use cached options because django will fetch them multiple times otherwise
            formfield.choices = self.training_types_choices

        return formfield

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(self, 'training_type_filter'):
            return qs.filter(training_type=self.training_type_filter)
        return qs.none()


@admin.register(models.UserTraining)
class UserTrainingAdmin(admin.ModelAdmin):

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .select_related('user')
                .prefetch_related('user__userinfo'))

    list_display = (
        "__str__",
        "enrolled_training_types",
        "missing_mandatory_training",
    )
    list_filter = (
        AutocompleteFilterFactory('user', 'user'),
        ('user__userinfo__country', DropdownFilter),
        'training__training_type'
    )
    autocomplete_fields = ('user',)

    def add_view(self, *args, **kwargs):
        self.inlines = []
        self.readonly_fields = []
        return super(UserTrainingAdmin, self).add_view(*args, **kwargs)

    def change_view(self, *args, **kwargs):
        self.inlines = [TrainingInline]
        self.readonly_fields = ["user"]
        return super(UserTrainingAdmin, self).change_view(*args, **kwargs)

    def enrolled_training_types(self, obj):
        return format_html('<br>'.join(str(x) for x in list(
            models.TrainingType.objects.filter(country=obj.user.userinfo.country,
                                               training__user_training=obj).distinct())))

    def missing_mandatory_training(self, obj):
        return format_html('<br>'.join(str(x) for x in list(
            models.TrainingType.objects.filter(country=obj.user.userinfo.country, mandatory=True).exclude(
                training__user_training=obj).distinct())))

    def get_inline_instances(self, request, obj=None):
        """This method will create few dynamic inlines grouped on TrainingType."""
        inlines = []

        # if this is change_view (don't display anything on add_view)
        if obj:

            # Fetch all training types that are already associated with user.
            enrolled_training_types = models.TrainingType.objects.filter(country=obj.user.userinfo.country,
                                                                         training__user_training=obj).distinct()
            # Fetch remaining training types that user can possibly have (filter by country)
            available_training_types = models.TrainingType.objects.filter(country=obj.user.userinfo.country).exclude(
                training__user_training=obj).distinct()

            # For every active training, add separate and tweaked inline
            for training_type in enrolled_training_types:
                training_inline = TrainingInline(self.model, self.admin_site)
                # Set naming
                training_inline.verbose_name = training_type
                training_inline.verbose_name_plural = "{training_type} - Trainings".format(training_type=training_type)
                # See `formfield_for_foreignkey()` and `get_queryset()` methods in `TrainingInline` class
                training_inline.training_types_choices = ((training_type.pk, str(training_type)),)
                training_inline.training_type_filter = training_type
                # Add to inlines which should be be display
                inlines.append(training_inline)

            # If there are any remaining training types, display inline for them.
            if available_training_types:
                general_training_inline = TrainingInline(self.model, self.admin_site)
                general_training_inline.extra = 1
                general_training_inline.training_types_choices = [(None, "---------")] \
                                                                 + [(i.pk, str(i)) for i in available_training_types]
                inlines.append(general_training_inline)

        return inlines
