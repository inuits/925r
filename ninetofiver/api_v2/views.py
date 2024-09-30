"""925r API v2 views."""
import datetime
import logging

import dateutil
from django.contrib.auth import models as auth_models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.db.models import Q, Prefetch
from rest_framework import mixins, permissions, viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from ninetofiver.api_v2 import serializers, filters
from ninetofiver import models, feeds, calculation, redmine
from ninetofiver.views import BaseTimesheetContractPdfExportServiceAPIView
from ninetofiver.exceptions import InvalidRedmineUserException

log = logging.getLogger(__name__)


class MeAPIView(APIView):
    """Get the currently authenticated user."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        entity = request.user
        data = serializers.MeSerializer(entity, context={'request': request}).data
        return Response(data)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve users."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.UserSerializer
    filterset_class = filters.UserFilter
    queryset = (auth_models.User.objects
                .exclude(is_active=False)
                .order_by('-date_joined')
                .select_related('userinfo'))


class LeaveTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve leave types."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.LeaveTypeSerializer
    queryset = models.LeaveType.objects.all()


class ContractRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve contract roles."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.ContractRoleSerializer
    queryset = models.ContractRole.objects.all()


class PerformanceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve performance types."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.PerformanceTypeSerializer
    queryset = models.PerformanceType.objects.all()


class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve locations."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.LocationSerializer
    queryset = models.Location.objects.all()


class HolidayViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve holidays."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.HolidaySerializer
    filterset_class = filters.HolidayFilter
    queryset = models.Holiday.objects.all()


class ContractViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve contracts."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.ContractSerializer
    filterset_class = filters.ContractFilter
    queryset = (models.Contract.objects.all()
                .select_related('company', 'customer')
                .prefetch_related(
        Prefetch('performance_types', queryset=(models.PerformanceType.objects
                                                .non_polymorphic())),
        Prefetch('attachments', queryset=(models.Attachment.objects
                                          .non_polymorphic())),
        Prefetch('contract_groups', queryset=(models.ContractGroup.objects
                                              .non_polymorphic())))
                .distinct())

    def get_queryset(self):
        return self.queryset.filter(contractuser__user=self.request.user)


class ContractUserViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve contract users."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.ContractUserSerializer
    filterset_class = filters.ContractUserFilter
    queryset = (models.ContractUser.objects.all()
                .select_related('contract', 'contract__customer', 'contract_role', 'user')
                .distinct())

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class TimesheetViewSet(viewsets.ModelViewSet):
    """CRUD timesheets."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.TimesheetSerializer
    filterset_class = filters.TimesheetFilter
    queryset = models.Timesheet.objects.all()

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_destroy(self, instance):
        if instance.status != models.STATUS_ACTIVE:
            raise ValidationError({'status': _('Only active timesheets can be deleted.')})
        return super().perform_destroy(instance)


class LeaveViewSet(viewsets.ModelViewSet):
    """CRUD leave."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.LeaveSerializer
    filterset_class = filters.LeaveFilter
    queryset = (models.Leave.objects.all()
                .select_related('leave_type')
                .prefetch_related('leavedate_set'))

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_destroy(self, instance):
        if instance.status not in [models.STATUS_DRAFT, models.STATUS_PENDING]:
            raise ValidationError({'status': _('Only draft/pending leave can be deleted.')})
        return super().perform_destroy(instance)


class WhereaboutViewSet(viewsets.ModelViewSet):
    """CRUD whereabouts."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.WhereaboutSerializer
    filterset_class = filters.WhereaboutFilter
    queryset = (models.Whereabout.objects.all()
                .select_related('location'))

    def get_queryset(self):
        return self.queryset.filter(timesheet__user=self.request.user)


class PerformanceViewSet(viewsets.ModelViewSet):
    """CRUD performance."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.PerformanceSerializer
    filterset_class = filters.PerformanceFilter
    queryset = (models.Performance.objects.all()
                .select_related('contract', 'contract__customer'))

    def get_queryset(self):
        return self.queryset.filter(timesheet__user=self.request.user)


class AttachmentViewSet(viewsets.ModelViewSet):
    """CRUD attachments."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = serializers.AttachmentSerializer
    filterset_class = filters.AttachmentFilter
    queryset = (models.Attachment.objects.all())

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_destroy(self, instance):
        # Don't allow deleting of attachment if the attached leave/timesheet is already closed/approved/rejected
        if (models.Timesheet.objects.filter(~Q(status=models.STATUS_ACTIVE), attachments=instance).count() or
                models.Leave.objects.filter(Q(status=models.STATUS_APPROVED) | Q(status=models.STATUS_REJECTED),
                                            attachments=instance)):
            raise ValidationError(_('Attachments linked to finalized timesheets or leaves cannot be deleted.'))
        return super().perform_destroy(instance)


class TimesheetContractPdfDownloadAPIView(BaseTimesheetContractPdfExportServiceAPIView):
    """Export a timesheet contract to PDF."""

    permission_classes = (permissions.IsAuthenticated,)

    def resolve_user_timesheet_contracts(self, context):
        """Resolve the users, timesheets and contracts for this export."""
        user = context['view'].request.user
        timesheet = get_object_or_404(models.Timesheet, pk=context.get('timesheet_pk', None), user=user)
        contract = get_object_or_404(models.Contract.objects.distinct(), pk=context.get('contract_pk', None))
        return [[user, timesheet, contract]]


class LeaveFeedAPIView(APIView):
    """Leave ICS feed."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        return feeds.LeaveFeed().__call__(request)


class UserLeaveFeedAPIView(APIView):
    """User-specific leave ICS feed."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, user_username=None, format=None):
        username = request.parser_context['kwargs'].get('user_username', None)
        user = get_object_or_404(auth_models.User, username=username, is_active=True) if username else request.user
        return feeds.UserLeaveFeed().__call__(request, user=user)


class WhereaboutFeedAPIView(APIView):
    """Whereabout ICS feed."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        return feeds.WhereaboutFeed().__call__(request)


class UserWhereaboutFeedAPIView(APIView):
    """User-specific whereabout ICS feed."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, user_username=None, format=None):
        username = request.parser_context['kwargs'].get('user_username', None)
        user = get_object_or_404(auth_models.User, username=username, is_active=True) if username else request.user
        return feeds.UserWhereaboutFeed().__call__(request, user=user)


class PerformanceImportAPIView(APIView):
    """Gets performances from external sources and returns them to be imported."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        from_date = request.query_params.get('from', str(datetime.date.today()))
        until_date = request.query_params.get('until', str(datetime.date.today()))

        data = {
            'count': 0,
            'previous': None,
            'next': None,
            'results': [],
        }

        # Redmine
        try:
            redmine_data = redmine.get_user_redmine_performances(request.user, from_date=from_date, to_date=until_date)
        except InvalidRedmineUserException as exc:
            data = {
                'message': str(exc)
            }
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        data['results'] += redmine_data
        data['count'] = len(data['results'])

        return Response(data)


class RangeAvailabilityAPIView(APIView):
    """Get availability for all active users."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        """Defines the entrypoint of the retrieval."""
        from_date = dateutil.parser.parse(request.query_params.get('from', None)).date()
        until_date = dateutil.parser.parse(request.query_params.get('until', None)).date()

        users = auth_models.User.objects.filter(is_active=True)
        users = users if not request.query_params.get('user', None) else \
            users.filter(id__in=list(map(int, request.query_params.get('user', None).split(','))))

        data = calculation.get_availability(users, from_date, until_date, serialize=True)

        return Response(data, status=status.HTTP_200_OK)


class RangeInfoAPIView(APIView):
    """Calculates and returns information for a given date range."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        """Get date range information."""
        user = request.user

        from_date = dateutil.parser.parse(request.query_params.get('from', None)).date()
        until_date = dateutil.parser.parse(request.query_params.get('until', None)).date()
        daily = request.query_params.get('daily', 'false') == 'true'
        detailed = request.query_params.get('detailed', 'false') == 'true'
        summary = request.query_params.get('summary', 'false') == 'true'

        data = calculation.get_range_info([user], from_date, until_date, daily=daily, detailed=detailed,
                                          summary=summary, serialize=True)
        data = data[user.id]

        return Response(data)


class EventsAPIView(APIView):
    """Get events."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        """Defines the entrypoint of the retrieval."""
        from_date = dateutil.parser.parse(request.query_params.get('from', None))
        until_date = dateutil.parser.parse(request.query_params.get('until', None))

        events = (
            models.Event.objects.all()
            .filter(
                (Q(starts_at__range=(from_date, until_date)) | Q(ends_at__range=(from_date, until_date))) |
                (Q(starts_at__lte=from_date) & Q(ends_at__gte=until_date)) |
                (Q(starts_at__gte=from_date) & Q(ends_at__lte=until_date))
            )
            .order_by('starts_at')
        )

        data = serializers.EventSerializer(events, many=True).data

        return Response(data, status=status.HTTP_200_OK)


class QuotesAPIView(APIView):
    """Get quotes."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        """Defines the entrypoint of the retrieval."""

        quotes = (
            models.Quote.objects.all()
        )

        quotes = [quote for quote in quotes if quote.is_today]

        if len(quotes) == 0:
            quotes = (
                models.Quote.objects.filter(Q(recurrences__exact=''))
            )

        data = serializers.QuoteSerializer(quotes, many=True).data

        return Response(data, status=status.HTTP_200_OK)
