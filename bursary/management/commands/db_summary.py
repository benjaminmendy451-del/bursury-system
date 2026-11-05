"""Print a short summary of what is in the database.

Run:  python manage.py db_summary
"""
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count

from bursary.models import Application, BursaryRound, Document, Institution, StudentProfile, Ward


class Command(BaseCommand):
    help = "Show a short summary of the database: connection, row counts, applications and recent changes."

    def handle(self, *args, **options):
        out = self.stdout.write
        settings_dict = connection.settings_dict
        connection.ensure_connection()

        out(self.style.MIGRATE_HEADING("Database"))
        out(f"  Engine:     {connection.vendor}")
        out(f"  Name:       {settings_dict.get('NAME')}")
        out(f"  Host:       {settings_dict.get('HOST') or 'local file'}")
        out(self.style.SUCCESS("  Connection: OK"))

        out(self.style.MIGRATE_HEADING("\nRows held"))
        counts = [
            ("Users", User.objects.count()),
            ("Students", StudentProfile.objects.count()),
            ("Bursary rounds", BursaryRound.objects.count()),
            ("Applications", Application.objects.count()),
            ("Documents", Document.objects.count()),
            ("Wards", Ward.objects.count()),
            ("Institutions", Institution.objects.count()),
        ]
        for label, number in counts:
            out(f"  {label:<16}{number:>8,}")

        out(self.style.MIGRATE_HEADING("\nApplications by status"))
        by_status = dict(Application.objects.values_list("status").annotate(n=Count("id")))
        for value, label in Application.Status.choices:
            out(f"  {label:<16}{by_status.get(value, 0):>8,}")

        out(self.style.MIGRATE_HEADING("\nBursary rounds"))
        for bursary_round in BursaryRound.objects.all():
            out(f"  {bursary_round.name}: budget KES {bursary_round.budget:,.0f}, "
                f"awarded KES {bursary_round.total_awarded:,.0f}, "
                f"remaining KES {bursary_round.remaining_budget:,.0f}")
        if not BursaryRound.objects.exists():
            out("  No rounds yet.")

        out(self.style.MIGRATE_HEADING("\nLatest 5 committee changes"))
        entries = LogEntry.objects.select_related("user").order_by("-action_time")[:5]
        for entry in entries:
            out(f"  {entry.action_time:%Y-%m-%d %H:%M}  {entry.user}  {entry.object_repr}: "
                f"{entry.get_change_message()}")
        if not entries:
            out("  No changes recorded yet.")
