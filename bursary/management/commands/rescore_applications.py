"""Work out the suggested need score for every application.

Run once after adding need-scoring (to score applications that already
exist), and again whenever you change the NEED_SCORING weights in settings:

    python manage.py rescore_applications
"""
from django.core.management.base import BaseCommand

from bursary.models import Application
from bursary.scoring import compute_need_score


class Command(BaseCommand):
    help = "Recalculate the suggested need score for all applications."

    def handle(self, *args, **options):
        applications = list(Application.objects.all())
        for application in applications:
            application.suggested_score = compute_need_score(application)[0]
        Application.objects.bulk_update(applications, ["suggested_score"])
        self.stdout.write(self.style.SUCCESS(f"Scored {len(applications)} application(s)."))
