"""Checks for dark mode, charts, the progress timeline and checklist, the award check page
(with its QR code) and the privacy page.  Run with:  python manage.py test"""
import importlib.util
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Application
from .reports import build_report
from .test_features import add_document, make_round
from .test_reports import make_application, make_student
from .views import _checklist, _short_name, _timeline, _verify_token

S = Application.Status


class LayoutTests(TestCase):
    def test_home_page_has_theme_button_and_footer_links(self):
        page = self.client.get(reverse("home"))
        self.assertContains(page, 'id="theme-toggle"')
        self.assertContains(page, reverse("privacy"))
        self.assertContains(page, 'id="how"')
        self.assertContains(page, 'id="contact"')

    def test_privacy_page_is_public(self):
        page = self.client.get(reverse("privacy"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "test information only")


class StudentPageTests(TestCase):
    def setUp(self):
        self.round = make_round()
        self.student = make_student(1, "Nairobi")
        self.application = make_application(self.round, self.student, S.SUBMITTED, 10000)
        self.client.login(username="student1", password="pass12345")

    def test_empty_dashboard_invites_the_student_to_apply(self):
        Application.objects.all().delete()
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "No applications yet")
        self.assertContains(page, "See open bursaries")

    def test_detail_page_shows_timeline_and_checklist(self):
        page = self.client.get(reverse("application_detail", args=[self.application.pk]))
        self.assertContains(page, "Application checklist")
        self.assertContains(page, "documents 0% complete")
        self.assertContains(page, "Review by the committee")

    def test_checklist_percentage_follows_uploaded_documents(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            add_document(self.application, "id")
            add_document(self.application, "fee_statement")
            add_document(self.application, "other")      # optional, never counted
            items, percent = _checklist(self.application)
        self.assertEqual(percent, 50)
        self.assertEqual([item["done"] for item in items], [True, True, True, False, False])

    def test_timeline_for_each_stage(self):
        states = lambda: [step[3] for step in _timeline(self.application)]
        self.assertEqual(states(), ["done", "current", "todo"])
        self.application.status = S.UNDER_REVIEW
        self.assertEqual(states(), ["done", "current", "todo"])
        self.application.status = S.REJECTED
        self.assertEqual(states(), ["done", "done", "done"])
        self.assertIn("Rejected", _timeline(self.application)[2][0])


class AwardCheckTests(TestCase):
    def setUp(self):
        self.round = make_round()
        self.student = make_student(1, "Nairobi")
        self.student.full_name = "Amina Wanjiru Kamau"
        self.student.save()
        self.application = make_application(self.round, self.student, S.APPROVED, 20000, 15000)

    def test_short_name_hides_most_of_the_name(self):
        self.assertEqual(_short_name("Amina Wanjiru Kamau"), "Amina K.")
        self.assertEqual(_short_name("Amina"), "Amina")

    def test_valid_link_shows_the_award_without_private_details(self):
        token = _verify_token(self.application)
        page = self.client.get(reverse("verify_award", args=[token]))
        self.assertContains(page, "genuine")
        self.assertContains(page, "Amina K.")
        self.assertContains(page, "15,000")
        self.assertNotContains(page, "Wanjiru")
        self.assertNotContains(page, self.student.national_id)

    def test_tampered_link_is_not_found(self):
        token = _verify_token(self.application)
        self.assertEqual(self.client.get(reverse("verify_award", args=[token[:-2] + "xx"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("verify_award", args=["not-a-real-code"])).status_code, 404)

    def test_withdrawn_award_no_longer_verifies(self):
        token = _verify_token(self.application)
        Application.objects.filter(pk=self.application.pk).update(status=S.REJECTED)
        page = self.client.get(reverse("verify_award", args=[token]))
        self.assertEqual(page.status_code, 404)
        self.assertContains(page, "could not verify", status_code=404)

    def test_award_letter_carries_the_check_link(self):
        self.client.login(username="student1", password="pass12345")
        letter = self.client.get(reverse("award_letter", args=[self.application.pk]))
        self.assertContains(letter, "/verify/")
        self.assertContains(letter, "genuine")

    def test_award_letter_has_a_qr_code_when_segno_is_installed(self):
        if importlib.util.find_spec("segno") is None:
            self.skipTest("segno is not installed")
        self.client.login(username="student1", password="pass12345")
        letter = self.client.get(reverse("award_letter", args=[self.application.pk]))
        self.assertContains(letter, "<svg")


class ReportChartTests(TestCase):
    def setUp(self):
        self.round = make_round()
        make_application(self.round, make_student(1, "Nairobi"), S.APPROVED, 20000, 15000)
        make_application(self.round, make_student(2, "Nairobi"), S.SUBMITTED, 10000)
        make_application(self.round, make_student(3, "Kiambu"), S.REJECTED, 30000)
        make_application(self.round, make_student(4, "Kiambu"), S.APPROVED, 30000, 25000)

    def test_chart_data(self):
        charts = build_report(self.round)["charts"]
        self.assertEqual(charts["total"], 4)
        counts = {item["label"]: item["count"] for item in charts["legend"]}
        self.assertEqual(counts["Approved"], 2)
        self.assertEqual(counts["Under review"], 0)
        self.assertTrue(charts["gradient"].startswith("conic-gradient("))
        self.assertEqual(charts["bars"][0]["width"], 100)
        self.assertEqual(len(charts["bars"]), 2)

    def test_empty_report_still_draws(self):
        Application.objects.all().delete()
        charts = build_report(self.round)["charts"]
        self.assertEqual(charts["total"], 0)
        self.assertIn("#e5ebe7", charts["gradient"])
        self.assertEqual(charts["bars"], [])

    def test_reports_page_shows_the_charts(self):
        User.objects.create_superuser("boss", "boss@example.com", "pass12345")
        self.client.login(username="boss", password="pass12345")
        page = self.client.get(reverse("reports"), {"round": self.round.pk})
        self.assertContains(page, "Status at a glance")
        self.assertContains(page, "class=\"donut\"")
