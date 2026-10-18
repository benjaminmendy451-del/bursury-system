"""Create the "Committee" group with the permissions reviewers need.

Run once after the first migrate:  python manage.py setup_committee
Then, in /admin/, create a user, tick "Staff status" and add them to the
"Committee" group. They can review applications but cannot delete anything
or manage other users.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

CODENAMES = [
    "view_bursaryround", "view_studentprofile",
    "view_application", "change_application",
    "view_document",
]


class Command(BaseCommand):
    help = "Create the Committee group with review permissions."

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name="Committee")
        perms = Permission.objects.filter(content_type__app_label="bursary", codename__in=CODENAMES)
        group.permissions.set(perms)
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} 'Committee' group with {perms.count()} permissions."))
