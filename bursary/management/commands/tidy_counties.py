from django.core.management.base import BaseCommand

from bursary.counties import canonical_county
from bursary.models import StudentProfile


class Command(BaseCommand):
    help = "Rewrite county names typed by students to the official spelling (e.g. 'kiambu county' -> 'Kiambu')."

    def handle(self, *args, **options):
        fixed, unknown = 0, []
        for profile in StudentProfile.objects.all():
            official = canonical_county(profile.county)
            if official is None:
                unknown.append(f"{profile.full_name}: '{profile.county}'")
            elif official != profile.county:
                profile.county = official
                profile.save(update_fields=["county"])
                fixed += 1
        self.stdout.write(self.style.SUCCESS(f"Fixed {fixed} profile(s)."))
        for line in unknown:
            self.stdout.write(self.style.WARNING(f"Not recognised, fix by hand in the admin: {line}"))
