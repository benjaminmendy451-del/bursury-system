"""Email students about rounds that are about to close.

    python manage.py send_reminders             # send the reminders
    python manage.py send_reminders --dry-run   # only show how many would go out

Two kinds of reminder, for every open round that closes in 3, 1 or 0 days:
  1. Students who have NOT applied yet: "this round closes soon".
  2. Students who applied but have not uploaded all their documents.

Because reminders go out only on those days, you can run this command once a
day (a scheduled task) and nobody is emailed again and again. Use --days to
change the days, for example --days 7,3,1,0.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from bursary.models import Application, BursaryRound, Document, StudentProfile
from bursary.notifications import send_email

WAITING = (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW)


def _when(days_left):
    if days_left == 0:
        return "today"
    return "tomorrow" if days_left == 1 else f"in {days_left} days"


class Command(BaseCommand):
    help = "Email students about rounds closing soon and about missing documents."

    def add_arguments(self, parser):
        parser.add_argument("--days", default="3,1,0",
                            help="Remind when a round has this many days left (default 3,1,0).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Count the reminders without sending any.")

    def handle(self, *args, **options):
        try:
            days = {int(part) for part in options["days"].split(",") if part.strip()}
        except ValueError:
            raise CommandError("--days must be numbers separated by commas, for example 3,1,0")
        dry = options["dry_run"]
        today = timezone.localdate()
        site = settings.SITE_URL.rstrip("/")
        labels = dict(Document.Kind.choices)
        required = [kind for kind in labels if kind != Document.Kind.OTHER]
        closing_count = docs_count = 0

        for bursary_round in BursaryRound.objects.filter(is_active=True):
            if not bursary_round.is_open:
                continue
            days_left = (bursary_round.closes_on - today).days
            if days_left not in days:
                continue

            applied = bursary_round.applications.values_list("student_id", flat=True)
            for profile in StudentProfile.objects.exclude(pk__in=list(applied)).select_related("user"):
                if not profile.user.email:
                    continue
                closing_count += 1
                if not dry:
                    send_email(
                        [profile.user.email], f"Closing {_when(days_left)}: {bursary_round.name}",
                        f"Hello {profile.full_name},\n\n"
                        f"{bursary_round.name} closes {_when(days_left)} "
                        f"({bursary_round.closes_on:%d %B %Y}). You have not applied yet.\n"
                        f"Log in to apply:\n{site}/dashboard/\n\nBursaryNexa Committee")

            waiting = (bursary_round.applications.filter(status__in=WAITING)
                       .select_related("student__user").prefetch_related("documents"))
            for application in waiting:
                have = {document.kind for document in application.documents.all()}
                missing = [labels[kind] for kind in required if kind not in have]
                email = application.student.user.email
                if not missing or not email:
                    continue
                docs_count += 1
                if not dry:
                    send_email(
                        [email], f"Documents needed: {bursary_round.name}",
                        f"Hello {application.student.full_name},\n\n"
                        f"Your application for {bursary_round.name} is missing: {', '.join(missing)}.\n"
                        f"The round closes {_when(days_left)}. Please upload them here:\n"
                        f"{site}/applications/{application.pk}/\n\nBursaryNexa Committee")

        verb = "Would send" if dry else "Sent"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {closing_count} closing-soon reminder(s) and {docs_count} missing-document reminder(s)."))
