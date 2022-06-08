"""ninetofiver URL Configuration"""
from django.urls import include
from django.urls import re_path
from django.urls import path
from django.conf import settings

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views.generic.base import TemplateView
from rest_framework import routers
# from rest_framework.urlpatterns import format_suffix_patterns
from django_downloadview import ObjectDownloadView
from oauth2_provider import views as oauth2_views
from django_registration.backends.activation import views as registration_views
from ninetofiver import views, models


urlpatterns = [
    path('api/v2/', include('ninetofiver.api_v2.urls', namespace='ninetofiver_api_v2')),
]

router = routers.DefaultRouter()

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browseable API.
urlpatterns += [
    path('', views.home_view, name='home'),
    path('api-docs/', views.api_docs_view, name='api_docs'),
    path('api-docs/swagger_ui/', views.api_docs_swagger_ui_view, name='api_docs_swagger_ui'),
    path('api-docs/redoc/', views.api_docs_redoc_view, name='api_docs_redoc'),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),

    # OAuth2
    path('oauth/v2/', include(
        ([
            path('authorize/', oauth2_views.AuthorizationView.as_view(template_name='ninetofiver/oauth2/authorize.pug'), name="authorize"),
            path('token/', oauth2_views.TokenView.as_view(), name="token"),
            path('revoke_token/', oauth2_views.RevokeTokenView.as_view(), name="revoke-token"),
            path('applications/', oauth2_views.ApplicationList.as_view(template_name='ninetofiver/oauth2/applications/list.pug'), name="list"),
            path('applications/register/', oauth2_views.ApplicationRegistration.as_view(template_name='ninetofiver/oauth2/applications/register.pug'), name="register"),
            path('applications/<int:pk>/', oauth2_views.ApplicationDetail.as_view(template_name='ninetofiver/oauth2/applications/detail.pug'), name="detail"),
            path('applications/<int:pk>/delete/', oauth2_views.ApplicationDelete.as_view(template_name='ninetofiver/oauth2/applications/delete.pug'), name="delete"),
            path('applications/<int:pk>/update/', oauth2_views.ApplicationUpdate.as_view(template_name='ninetofiver/oauth2/applications/update.pug'), name="update"),
            path('authorized_tokens/', oauth2_views.AuthorizedTokensListView.as_view(template_name='ninetofiver/oauth2/tokens/list.pug'), name="authorized-token-list"),
            path('authorized_tokens/<int:pk>/delete/', oauth2_views.AuthorizedTokenDeleteView.as_view(template_name='ninetofiver/oauth2/tokens/delete.pug'), name="authorized-token-delete"),
        ], 'oauth_appname'),
        namespace='oauth2_provider',
    )),

    # Account
    path('accounts/profile/', views.account_view, name='account'),
    path('accounts/password/change/', auth_views.PasswordChangeView.as_view(template_name='ninetofiver/account/password_change.pug'), name='password_change'),
    path('accounts/password/change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='ninetofiver/account/password_change_done.pug'), name='password_change_done'),

    path('accounts/api_keys/', views.ApiKeyListView.as_view(), name='api-key-list'),
    path('accounts/api_keys/create/', views.ApiKeyCreateView.as_view(), name='api-key-create'),
    path('accounts/api_keys/<int:pk>/delete/', views.ApiKeyDeleteView.as_view(), name='api-key-delete'),

    # Auth
    path('auth/login/', auth_views.LoginView.as_view(template_name='ninetofiver/authentication/login.pug'), name='login'),
    path('auth/logout/', auth_views.LogoutView.as_view(template_name='ninetofiver/authentication/logout.pug'), name='logout'),
    path('auth/password/reset/', auth_views.PasswordResetView.as_view(template_name='ninetofiver/authentication/password_reset.pug'), name='password_reset'),
    path('auth/password/reset/done', auth_views.PasswordResetDoneView.as_view(template_name='ninetofiver/authentication/password_reset_done.pug'), name='password_reset_done'),
    re_path(r'^auth/password/reset/confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$', auth_views.PasswordResetConfirmView, {'template_name': 'ninetofiver/authentication/password_reset_confirm.pug'}, name='password_reset_confirm'),
    path('auth/password/reset/complete/', auth_views.PasswordResetDoneView.as_view(template_name='ninetofiver/authentication/password_reset_complete.pug'), name='password_reset_complete'),

    # Registration
    path(
        'auth/activate/complete/',
        TemplateView.as_view(template_name='ninetofiver/registration/activation_complete.pug'),
        name='registration_activation_complete',
    ),
    # The activation key can make use of any character from the
    # URL-safe base64 alphabet, plus the colon as a separator.
    path(
        'auth/activate/<str:activation_key>/',
        registration_views.ActivationView.as_view(template_name='ninetofiver/registration/activate.pug'),
        name='registration_activate',
    ),
    path(
        'auth/register/',
        registration_views.RegistrationView.as_view(
            template_name='ninetofiver/registration/register.pug',
            email_body_template='ninetofiver/registration/activation_email.txt',
            email_subject_template='ninetofiver/registration/activation_email_subject.txt',
        ),
        name='registration_register',
    ),
    path(
        'auth/register/complete/',
        TemplateView.as_view(template_name='ninetofiver/registration/register_complete.pug'),
        name='registration_complete',
    ),
    path(
        'auth/register/closed/',
        TemplateView.as_view(template_name='ninetofiver/registration/register_closed.pug'),
        name='registration_disallowed',
    ),

    # Silk (profiling)
    path('admin/silk/', include('silk.urls', namespace='silk')),

    # Django SQL explorer
    path('admin/sqlexplorer/', include('explorer.urls')),

    # Custom admin routes
    re_path(r'^admin/ninetofiver/leave/approve/(?P<leave_pk>[0-9,]+)/$', views.admin_leave_approve_view, name='admin_leave_approve'),  # noqa
    re_path(r'^admin/ninetofiver/leave/reject/(?P<leave_pk>[0-9,]+)/$', views.admin_leave_reject_view, name='admin_leave_reject'),  # noqa
    re_path(r'^admin/ninetofiver/timesheet/close/(?P<timesheet_pk>[0-9,]+)/$', views.admin_timesheet_close_view, name='admin_timesheet_close'),  # noqa
    re_path(r'^admin/ninetofiver/timesheet/activate/(?P<timesheet_pk>[0-9,]+)/$', views.admin_timesheet_activate_view, name='admin_timesheet_activate'),  # noqa
    path('admin/ninetofiver/report/', views.admin_report_index_view, name='admin_report_index'),  # noqa
    path('admin/ninetofiver/report/timesheet_contract_overview/', views.admin_report_timesheet_contract_overview_view, name='admin_report_timesheet_contract_overview'),  # noqa
    path('admin/ninetofiver/report/timesheet_overview/', views.admin_report_timesheet_overview_view, name='admin_report_timesheet_overview'),  # noqa
    path('admin/ninetofiver/report/timesheet_monthly_overview/', views.TimesheetMonthlyOverviewView.as_view(), name='admin_report_timesheet_monthly_overview'),  # noqa
    path('admin/ninetofiver/report/timesheet_overview_poland/', views.admin_report_timesheet_overview_poland_view, name='admin_report_timesheet_overview_poland'),  # noqa
    path('admin/ninetofiver/report/user_range_info/', views.admin_report_user_range_info_view, name='admin_report_user_range_info'),  # noqa
    path('admin/ninetofiver/report/user_leave_overview/', views.admin_report_user_leave_overview_view, name='admin_report_user_leave_overview'),  # noqa
    path('admin/ninetofiver/report/user_work_ratio_by_user/', views.admin_report_user_work_ratio_by_user_view, name='admin_report_user_work_ratio_by_user'),  # noqa
    path('admin/ninetofiver/report/user_work_ratio_by_month/', views.admin_report_user_work_ratio_by_month_view, name='admin_report_user_work_ratio_by_month'),  # noqa
    path('admin/ninetofiver/report/user_work_ratio_overview/', views.admin_report_user_work_ratio_overview_view, name='admin_report_user_work_ratio_overview'),  # noqa
    path('admin/ninetofiver/report/user_overtime_overview/', views.admin_report_user_overtime_overview_view, name='admin_report_user_overtime_overview'),  # noqa
    path('admin/ninetofiver/report/resource_availability_overview/', views.ResourceAvailabilityOverviewView.as_view(), name='admin_report_resource_availability_overview'),  # noqa
    path('admin/ninetofiver/report/expiring_consultancy_contract_overview/', views.admin_report_expiring_consultancy_contract_overview_view, name='admin_report_expiring_consultancy_contract_overview'),  # noqa
    path('admin/ninetofiver/report/invoiced_consultancy_contract_overview/', views.admin_report_invoiced_consultancy_contract_overview_view, name='admin_report_invoiced_consultancy_contract_overview'), # noqa
    path('admin/ninetofiver/report/expiring_support_contract_overview/', views.admin_report_expiring_support_contract_overview_view, name='admin_report_expiring_support_contract_overview'),  # noqa
    path('admin/ninetofiver/report/project_contract_overview/', views.admin_report_project_contract_overview_view, name='admin_report_project_contract_overview'),  # noqa
    path('admin/ninetofiver/report/project_contract_budget_overview/', views.admin_report_project_contract_budget_overview_view, name='admin_report_project_contract_budget_overview'),  # noqa
    path('admin/ninetofiver/report/expiring_user_training_overview/', views.admin_report_expiring_user_training_overview_view, name='admin_report_expiring_user_training_overview_view'),  # noqa
    re_path(r'^admin/ninetofiver/timesheet_contract_pdf_export/(?P<user_timesheet_contract_pks>[0-9:,]+)/$', views.AdminTimesheetContractPdfExportView.as_view(), name='admin_timesheet_contract_pdf_export'),  # noqa
    path('admin/ninetofiver/report/internal_availability_overview/', views.admin_report_internal_availability_overview_view, name='admin_report_internal_availability_overview_view'),  # noqa
    # Admin
    path('admin/', admin.site.urls),
]


# if settings.DEBUG:
#     import debug_toolbar
#
#     urlpatterns += [
#         # django debug toolbar - only for dev
#         path('__debug__/', include(debug_toolbar.urls)),
#     ]
