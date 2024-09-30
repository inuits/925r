"""925r API v2 URLs."""
from django.urls import include
from django.urls import path
from rest_framework import routers
from django_downloadview import ObjectDownloadView
from ninetofiver.api_v2 import views
from ninetofiver import models

app_name = "ninetofiver_api_v2"

urlpatterns = [
    # path('api/', views.schema_view, name='api_docs'),
]

router = routers.SimpleRouter()
router.register(r'users', views.UserViewSet)
router.register(r'leave_types', views.LeaveTypeViewSet)
router.register(r'contract_roles', views.ContractRoleViewSet)
router.register(r'performance_types', views.PerformanceTypeViewSet)
router.register(r'locations', views.LocationViewSet)
router.register(r'holidays', views.HolidayViewSet)
router.register(r'timesheets', views.TimesheetViewSet)
router.register(r'leave', views.LeaveViewSet)
router.register(r'contracts', views.ContractViewSet)
router.register(r'contract_users', views.ContractUserViewSet)
router.register(r'whereabouts', views.WhereaboutViewSet)
router.register(r'performances', views.PerformanceViewSet)
router.register(r'attachments', views.AttachmentViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browseable API.
urlpatterns += [
    path('', include(router.urls + [
        path('me/', views.MeAPIView.as_view(), name='me'),
        path('feeds/leave/all.ics', views.LeaveFeedAPIView.as_view()),
        path('feeds/leave/me.ics', views.UserLeaveFeedAPIView.as_view()),
        path('feeds/leave/<str:user_username>.ics', views.UserLeaveFeedAPIView.as_view()),
        path('feeds/whereabouts/all.ics', views.WhereaboutFeedAPIView.as_view()),
        path('feeds/whereabouts/me.ics', views.UserWhereaboutFeedAPIView.as_view()),
        path('feeds/whereabouts/<str:user_username>.ics', views.UserWhereaboutFeedAPIView.as_view()),

        path('downloads/attachments/<slug:slug>/', ObjectDownloadView.as_view(model=models.Attachment, file_field='file'), name='download_attachment'),
        path('downloads/company_logos/<int:pk>/', ObjectDownloadView.as_view(model=models.Company, file_field='logo', attachment=False), name='download_company_logo'),
        path('downloads/timesheet_contract_pdf/<int:timesheet_pk>/<int:contract_pk>/', views.TimesheetContractPdfDownloadAPIView.as_view(), name='download_timesheet_contract_pdf'),

        path('imports/performances/', views.PerformanceImportAPIView.as_view()),
        path('range_info/', views.RangeInfoAPIView.as_view()),
        path('range_availability/', views.RangeAvailabilityAPIView.as_view()),
        path('events/', views.EventsAPIView.as_view()),
        path('quotes/', views.QuotesAPIView.as_view()),
    ])),
]
