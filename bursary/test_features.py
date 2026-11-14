"""Checks for the extra committee filters, the report filters and the reminder emails.
Run with:  python manage.py test"""
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Application, BursaryRound, Document
from .reports import build_report, county_options
from .test_reports import make_application, make_student

S = Application.Status


def make_round(days_left=5, name="Test Round", budget="100000"):
    today = timezone.localdate()
    return BursaryRound.objects.create(
        name=name, budget=Decimal(budget), opens_on=today - timedelta(days=5),
        closes_on=today + timedelta(days=days_left))


def add_document(application, kind):
    return Document.objects.create(
        application=application, kind=kind,
        file=SimpleUploadedFile(f"{kind}.pdf", b"%PDF-1.4 test", content_type="application/pdf"))


class CommitteeFilterTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("boss", "boss@example.com", "pass12345")
        self.client.login(username="boss", password="pass12345")
        self.round = make_round()
        self.small = make_application(self.round, make_student(1, "Nairobi", institution="Alpha College"),
                                      S.SUBMITTED, 10000)
        self.middle = make_application(self.round, make_student(2, "Kiambu", institution="Beta College"),
                                       S.APPROVED, 30000, 20000)
        self.large = make_application(self.round, make_student(3, "Nairobi", institution="Alpha College"),
                                      S.REJECTED, 80000)
        self.url = reverse("admin:bursary_application_changelist")

    def shown(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return {a.pk for a in response.context["cl"].result_list}

    def test_amount_filter(self):
        self.assertEqual(self.shown(amount="low"), {self.small.pk})
        self.assertEqual(self.shown(amount="mid"), {self.middle.pk})
        self.assertEqual(self.shown(amount="high"), {self.large.pk})

    def test_decision_filter(self):
        self.assertEqual(self.shown(decision="awaiting"), {self.small.pk})
        self.assertEqual(self.shown(decision="decided"), {self.middle.pk, self.large.pk})

    def test_institution_filter(self):
        self.assertEqual(self.shown(student__institution="Alpha College"), {self.small.pk, self.large.pk})

    def test_submitted_date_filter_opens(self):
        self.assertEqual(self.shown(submitted_at__gte=(timezone.localdate() - timedelta(days=1)).isoformat()),
                         {self.small.pk, self.middle.pk, self.large.pk})

    def test_documents_filter(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            for kind in ("id", "fee_statement", "admission", "income"):
                add_document(self.middle, kind)
            add_document(self.small, "id")
            add_document(self.small, "id")     # the same kind twice must not count twice
            add_document(self.large, "other")  # "other" is not a required document
            self.assertEqual(self.shown(docs="complete"), {self.middle.pk})
            self.assertEqual(self.shown(docs="missing"), {self.small.pk, self.large.pk})
            self.assertEqual(self.shown(docs="none"), {self.large.pk})

    def test_summary_follows_the_filters(self):
        response = self.client.get(self.url, {"decision": "decided"})
        summary = response.context_data["summary"]
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["requested"], Decimal("110000"))
        self.assertEqual(summary["awarded"], Decimal("20000"))
        self.assertContains(response, "Showing")

    def test_status_shows_as_a_coloured_label(self):
        self.assertContains(self.client.get(self.url), "border-radius:999px")

    def test_all_filters_work_together(self):
        response = self.client.get(self.url, {"decision": "decided", "amount": "mid", "docs": "missing",
                                              "student__county": "Kiambu"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual({a.pk for a in response.context["cl"].result_list}, {self.middle.pk})


class ReportFilterTests(TestCase):
    def setUp(self):
        self.round = make_round()
        make_application(self.round, make_student(1, "Nairobi"), S.APPROVED, 20000, 15000)
        make_application(self.round, make_student(2, " nairobi "), S.SUBMITTED, 10000)
        make_application(self.round, make_student(3, "Kiambu"), S.APPROVED, 30000, 25000)

    def test_county_filter_ignores_capitals_and_spaces(self):
        report = build_report(self.round, county="NAIROBI")
        self.assertEqual(report["summary"]["applications"], 2)
        self.assertEqual(report["summary"]["requested"], Decimal("30000"))
        self.assertTrue(report["filtered"])

    def test_status_filter(self):
        report = build_report(self.round, status="approved")
        self.assertEqual(report["summary"]["applications"], 2)
        self.assertEqual(report["summary"]["awarded"], Decimal("40000"))

    def test_budget_always_covers_the_whole_round(self):
        report = build_report(self.round, county="Kiambu")
        self.assertEqual(report["summary"]["awarded"], Decimal("25000"))
        self.assertEqual(report["summary"]["remaining"], Decimal("60000"))  # 100000 - 15000 - 25000

    def test_unfiltered_report_is_unchanged(self):
        report = build_report(self.round)
        self.assertFalse(report["filtered"])
        self.assertEqual(report["summary"]["applications"], 3)
        self.assertEqual(report["summary"]["remaining"], Decimal("60000"))

    def test_bad_status_is_ignored(self):
        self.assertEqual(build_report(self.round, status="nonsense")["summary"]["applications"], 3)

    def test_county_options_are_tidy_and_unique(self):
        self.assertEqual(county_options(), ["Kiambu", "Nairobi"])

    def test_reports_page_and_csv_accept_the_filters(self):
        User.objects.create_superuser("boss", "boss@example.com", "pass12345")
        self.client.login(username="boss", password="pass12345")
        page = self.client.get(reverse("reports"), {"round": self.round.pk, "county": "Nairobi",
                                                    "status": "approved"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Clear filters")
        csv_response = self.client.get(reverse("reports_csv"), {"round": self.round.pk, "county": "Nairobi"})
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("Filters", csv_response.content.decode())


class ReminderTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("send_reminders", *args, stdout=out)
        return out.getvalue()

    def setUp(self):
        self.round = make_round(days_left=3)
        self.applied = make_student(1, "Nairobi")
        self.not_applied = make_student(2, "Kiambu")
        self.application = make_application(self.round, self.applied, S.SUBMITTED, 10000)
        mail.outbox.clear()

    def test_sends_closing_and_missing_document_reminders(self):
        self.run_command()
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ["student1@example.com", "student2@example.com"])
        subjects = {m.to[0]: m.subject for m in mail.outbox}
        self.assertIn("Closing", subjects["student2@example.com"])
        self.assertIn("Documents needed", subjects["student1@example.com"])

    def test_dry_run_sends_nothing(self):
        output = self.run_command("--dry-run")
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("Would send 1 closing-soon", output)
        self.assertIn("1 missing-document", output)

    def test_no_reminder_when_the_round_closes_later(self):
        BursaryRound.objects.update(closes_on=timezone.localdate() + timedelta(days=10))
        self.run_command()
        self.assertEqual(len(mail.outbox), 0)

    def test_days_option_changes_when_reminders_go_out(self):
        BursaryRound.objects.update(closes_on=timezone.localdate() + timedelta(days=7))
        self.run_command("--days", "7")
        self.assertEqual(len(mail.outbox), 2)

    def test_complete_documents_get_no_document_reminder(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            for kind in ("id", "fee_statement", "admission", "income"):
                add_document(self.application, kind)
            self.run_command()
        self.assertEqual([m.to[0] for m in mail.outbox], ["student2@example.com"])

    def test_decided_applications_are_not_chased(self):
        Application.objects.filter(pk=self.application.pk).update(status=S.APPROVED)
        self.run_command()
        self.assertEqual([m.to[0] for m in mail.outbox], ["student2@example.com"])

    def test_inactive_or_closed_rounds_are_skipped(self):
        BursaryRound.objects.update(is_active=False)
        self.run_command()
        self.assertEqual(len(mail.outbox), 0)

    def test_bad_days_value_gives_a_clear_error(self):
        with self.assertRaises(CommandError):
            self.run_command("--days", "soon")
