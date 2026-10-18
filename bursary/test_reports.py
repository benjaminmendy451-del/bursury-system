"""Checks for the committee reports page. Run with:  python manage.py test"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Application, BursaryRound, StudentProfile
from .reports import build_report


def make_student(number, county, ward="Kileleshwa", institution="Test University"):
    user = User.objects.create_user(f"student{number}", f"student{number}@example.com", "pass12345")
    return StudentProfile.objects.create(
        user=user, full_name=f"Student {number}", national_id=f"ID{number}", phone="0712345678",
        county=county, ward=ward, institution=institution, admission_number=f"ADM{number}",
        course_or_form="Course", year_of_study=1)


def make_application(bursary_round, student, status, requested, awarded=0):
    return Application.objects.create(
        bursary_round=bursary_round, student=student, annual_family_income=50000,
        dependants_in_school=1, total_fees=60000, fees_paid=0,
        amount_requested=requested, reason="Need help", status=status, amount_awarded=awarded)


class ReportNumbersTests(TestCase):
    def setUp(self):
        self.bursary_round = BursaryRound.objects.create(
            name="Test round", budget=Decimal("100000"),
            opens_on=date(2026, 1, 1), closes_on=date(2026, 12, 31))
        approved, submitted = Application.Status.APPROVED, Application.Status.SUBMITTED
        # Two Nairobi students spelled differently, one Kiambu student.
        make_application(self.bursary_round, make_student(1, "Nairobi"), approved, 20000, 15000)
        make_application(self.bursary_round, make_student(2, " nairobi "), submitted, 10000)
        make_application(self.bursary_round, make_student(3, "Kiambu"), approved, 30000, 25000)

    def test_summary_totals_and_budget(self):
        summary = build_report(self.bursary_round)["summary"]
        self.assertEqual(summary["applications"], 3)
        self.assertEqual(summary["requested"], Decimal("60000"))
        self.assertEqual(summary["awarded"], Decimal("40000"))
        self.assertEqual(summary["remaining"], Decimal("60000"))

    def test_counties_ignore_capitals_and_spaces(self):
        counties = {row["label"]: row for row in build_report(self.bursary_round)["counties"]}
        self.assertEqual(set(counties), {"Nairobi", "Kiambu"})
        self.assertEqual(counties["Nairobi"]["applications"], 2)
        self.assertEqual(counties["Nairobi"]["approved"], 1)
        self.assertEqual(counties["Nairobi"]["awarded"], Decimal("15000"))

    def test_only_approved_applications_count_as_awarded(self):
        total = build_report(self.bursary_round)["counties_total"]
        self.assertEqual(total["applications"], 3)
        self.assertEqual(total["awarded"], Decimal("40000"))


class ReportAccessTests(TestCase):
    def test_anonymous_visitors_are_sent_to_log_in(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, 302)

    def test_students_cannot_open_reports(self):
        make_student(1, "Nairobi")
        self.client.login(username="student1", password="pass12345")
        self.assertEqual(self.client.get(reverse("reports")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports_csv")).status_code, 403)

    def test_committee_can_open_page_and_download_csv(self):
        User.objects.create_superuser("boss", "boss@example.com", "pass12345")
        self.client.login(username="boss", password="pass12345")
        page = self.client.get(reverse("reports"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Reports")
        csv_response = self.client.get(reverse("reports_csv"))
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")


class CountyTests(TestCase):
    def test_typed_names_map_to_official_spelling(self):
        from .counties import canonical_county
        self.assertEqual(canonical_county(" kiambu COUNTY "), "Kiambu")
        self.assertEqual(canonical_county("Muranga"), "Murang'a")
        self.assertEqual(canonical_county("trans-nzoia"), "Trans Nzoia")
        self.assertEqual(canonical_county("Taita Taveta"), "Taita-Taveta")
        self.assertIsNone(canonical_county("Atlantis"))

    def test_there_are_47_counties(self):
        from .counties import COUNTIES
        self.assertEqual(len(COUNTIES), 47)
        self.assertEqual(len(set(COUNTIES)), 47)

    def test_registration_rejects_unlisted_county(self):
        from .forms import StudentRegistrationForm
        form = StudentRegistrationForm(data={"county": "Atlantis"})
        form.is_valid()
        self.assertIn("county", form.errors)


class ReferenceListTests(TestCase):
    base = {"username": "kim", "email": "kim@example.com", "password1": "Str0ng-pass-99",
            "password2": "Str0ng-pass-99", "full_name": "Kim", "national_id": "1", "phone": "0712345678",
            "county": "Nairobi", "admission_number": "A1", "course_or_form": "Form 4", "year_of_study": 1}

    def form(self, **extra):
        from .forms import StudentRegistrationForm
        return StudentRegistrationForm(data={**self.base, **extra})

    def test_free_text_still_works_before_lists_are_loaded(self):
        self.assertTrue(self.form(institution="Any School", ward="Anywhere").is_valid())

    def test_ward_must_belong_to_the_chosen_county(self):
        from .models import Ward
        Ward.objects.create(county="Kiambu", name="Ruiru")
        Ward.objects.create(county="Nairobi", name="Kileleshwa")
        self.assertTrue(self.form(institution="S", ward="Kileleshwa").is_valid())
        wrong = self.form(institution="S", ward="Ruiru")
        self.assertFalse(wrong.is_valid())
        self.assertIn("ward", wrong.errors)

    def test_institution_dropdown_and_not_listed_option(self):
        from .models import Institution
        Institution.objects.create(name="Alliance High School")
        self.assertTrue(self.form(institution="Alliance High School").is_valid())
        self.assertFalse(self.form(institution="Made up School").is_valid())
        self.assertFalse(self.form(institution="__other__").is_valid())  # needs a name
        ok = self.form(institution="__other__", institution_other="Small Academy")
        self.assertTrue(ok.is_valid())
        self.assertEqual(ok.cleaned_data["institution"], "Small Academy")
