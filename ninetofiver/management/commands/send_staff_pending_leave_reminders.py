"""Send staff a reminder about pending leaves."""
import logging
from datetime import date
from django.db.models import Q
from django.core.management.base import BaseCommand
from django.contrib.auth import models as auth_models
from django.utils.translation import gettext_lazy as _
from ninetofiver import models
from ninetofiver.utils import send_mail, get_users_with_permission


log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Send staff a reminder about pending leave."""

    args = ""
    help = "Send staff a reminder about pending leave"

    def handle(self, *args, **options):
        """Send staff a reminder about pending leave."""
        pending_leaves = models.Leave.objects.filter(status=models.STATUS_PENDING)
        pending_leave_count = pending_leaves.count()
        log.info("%s pending leave(s) found" % pending_leave_count)

        if pending_leave_count:
            recipients = get_users_with_permission(
                models.PERMISSION_RECEIVE_PENDING_LEAVE_REMINDER
            )
            for recipient in recipients:
                recipient_pending_leaves = []
                recipient_employment_contract = (
                    models.EmploymentContract.objects.filter(
                        Q(user=recipient)
                        & Q(started_at__lte=date.today())
                        & (Q(ended_at__gte=date.today()) | Q(ended_at__isnull=True))
                    )
                )
                if recipient_employment_contract.exists():
                    recipient_company = recipient_employment_contract.first().company
                else: 
                    continue
                for leave in pending_leaves:
                    user_employment_contract = models.EmploymentContract.objects.filter(
                        Q(user=leave.user)
                        & Q(started_at__lte=date.today())
                        & (Q(ended_at__gte=date.today()) | Q(ended_at__isnull=True))
                    )
                    if user_employment_contract.exists():
                        user_company = user_employment_contract.first().company
                        if user_company == recipient_company:
                            recipient_pending_leaves.append(leave)
                if recipient.email and recipient_pending_leaves:
                    log.info("Sending reminder to %s" % recipient.email)

                    send_mail(
                        recipient.email,
                        _("Pending leave awaiting your approval"),
                        "ninetofiver/emails/pending_leave_reminder.pug",
                        context={
                            "user": recipient,
                            "leaves": recipient_pending_leaves,
                            "leave_ids": ",".join([str(x.id) for x in pending_leaves]),
                            "leave_count": len(recipient_pending_leaves),
                            'company_id': recipient_company.id
                        },
                    )
