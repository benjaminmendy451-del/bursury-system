"""Checks for password reset, duplicate registration, award letters, audit log and admin filters.
Run with:  python manage.py test"""
from decimal import Decimal

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Application, BursaryRound, StudentProfile
from .test_reports import make_application, make_student


def make_round():
    from datetime import date, timedelta
    today = date.today()
    return BursaryRound.objects.create(
        name="Test Round", budget=Decimal("100000"), opens_on=today - timedelta(days=5),
        closes_on=today + timedelta(days=5))


class PasswordResetTests(TestCase):
    def test_reset_page_opens_and_email_is_sent(self):
        User.objects.create_user("amina", "amina@example.com", "pass12345")
        self.assertEqual(self.client.get(reverse("password_reset")).status_code, 200)
        response = self.client.post(reverse("password_reset"), {"email": "amina@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/reset/", mail.outbox[0].body)

    def test_unknown_email_sends_nothing_but_looks_the_same(self):
        response = self.client.post(reverse("password_reset"), {"email": "nobody@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)


class DuplicateRegistrationTests(TestCase):
    def _data(self, national_id, username):
        return {"username": username, "email": f"{username}@example.com", "password1": "Str0ngPass!word",
                "password2": "Str0ngPass!word", "full_name": "Test Student", "national_id": national_id,
                "phone": "0712345678", "county": "Nairobi", "ward": "", "institution": "Test University",
                "admission_number": "ADM001", "course_or_form": "Course", "year_of_study": 1}

    def test_same_admission_number_at_same_institution_is_blocked(self):
        user = User.objects.create_user("first", "first@example.com", "pass12345")
        StudentProfile.objects.create(
            user=user, full_name="First", national_id="111", phone="0711111111", county="Nairobi",
            institution="Test University", admission_number="ADM001", course_or_form="Course",
            year_of_study=1)
        response = self.client.post(reverse("register"), self._data("22222222", "second"))
        self.assertEqual(response.status_code, 200)  # form shown again with an error
        self.assertFalse(User.objects.filter(username="second").exists())
        self.assertContains(response, "already registered")


class AwardLetterTests(TestCase):
    def setUp(self):
        self.round = make_round()
        self.student = make_student(1, "Nairobi")
        self.other = make_student(2, "Nairobi")
        self.approved = make_application(self.round, self.student, Application.Status.APPROVED, 10000, 10000)
        self.pending = make_application(self.round, self.other, Application.Status.SUBMITTED, 5000)

    def test_owner_can_open_letter_for_approved_application(self):
        self.client.login(username="student1", password="pass12345")
        page = self.client.get(reverse("award_letter", args=[self.approved.pk]))
        self.assertContains(page, "10,000")

    def test_other_student_cannot_open_it(self):
        self.client.login(username="student2", password="pass12345")
        self.assertEqual(self.client.get(reverse("award_letter", args=[self.approved.pk])).status_code, 404)

    def test_no_letter_for_application_that_is_not_approved(self):
        self.client.login(username="student2", password="pass12345")
        self.assertEqual(self.client.get(reverse("award_letter", args=[self.pending.pk])).status_code, 404)


class ErrorPageTests(TestCase):
    def test_student_gets_friendly_403_on_reports(self):
        make_student(1, "Nairobi")
        self.client.login(username="student1", password="pass12345")
        response = self.client.get(reverse("reports"))
        self.assertContains(response, "have access", status_code=403)


class AdminImprovementsTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser("boss", "boss@example.com", "pass12345")
        self.client.login(username="boss", password="pass12345")
        self.round = make_round()
        self.student = make_student(1, "Nairobi")
        self.application = make_application(self.round, self.student, Application.Status.SUBMITTED, 10000)

    def test_bulk_action_is_written_to_the_audit_log(self):
        self.client.post(reverse("admin:bursary_application_changelist"), {
            "action": "mark_under_review", "_selected_action": [self.application.pk]})
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.application.pk),
                                                change_message__contains="Under review").exists())

    def test_score_band_filter_and_search_work(self):
        url = reverse("admin:bursary_application_changelist")
        self.assertEqual(self.client.get(url, {"band": "high"}).status_code, 200)
        self.assertEqual(self.client.get(url, {"band": "unscored"}).status_code, 200)
        page = self.client.get(url, {"q": self.student.admission_number})
        self.assertContains(page, "Student 1")

    def test_audit_log_page_opens(self):
        self.assertEqual(self.client.get(reverse("admin:admin_logentry_changelist")).status_code, 200)


class StudentDashboardTests(TestCase):
    def setUp(self):
        self.round = make_round()
        self.student = make_student(1, "Nairobi")
        self.application = make_application(self.round, self.student, Application.Status.SUBMITTED, 5000)
        self.second_round = make_round()  # a round the student has not applied to yet
        self.client.login(username="student1", password="pass12345")

    def test_dashboard_shows_missing_documents_progress_and_days_left(self):
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "please upload")
        self.assertContains(page, "Admission letter")
        self.assertContains(page, "Submitted")
        self.assertContains(page, "days left")
        self.assertContains(page, "My profile")

    def test_change_password_page_opens(self):
        self.assertEqual(self.client.get(reverse("password_change")).status_code, 200)


class DbSummaryCommandTests(TestCase):
    def test_summary_prints_counts_and_connection(self):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command("db_summary", stdout=out)
        text = out.getvalue()
        self.assertIn("Connection: OK", text)
        self.assertIn("Applications", text)


class LockoutLoginTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        User.objects.create_user("amina", "amina@example.com", "pass12345")

    def test_five_wrong_passwords_lock_the_account_for_a_while(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "amina", "password": "wrong"})
        # Even the right password is refused while locked.
        response = self.client.post(reverse("login"), {"username": "amina", "password": "pass12345"})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many failed attempts", status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_correct_login_still_works_and_resets_the_count(self):
        for _ in range(3):
            self.client.post(reverse("login"), {"username": "amina", "password": "wrong"})
        response = self.client.post(reverse("login"), {"username": "amina", "password": "pass12345"})
        self.assertEqual(response.status_code, 302)


class InputValidationTests(TestCase):
    def _data(self, **extra):
        data = {"username": "newstudent", "email": "new@example.com", "password1": "Str0ngPass!word",
                "password2": "Str0ngPass!word", "full_name": "New Student", "national_id": "12345678",
                "phone": "0712345678", "county": "Nairobi", "ward": "", "institution": "Test University",
                "admission_number": "ADM777", "course_or_form": "Course", "year_of_study": 1}
        data.update(extra)
        return data

    def test_bad_phone_is_rejected(self):
        response = self.client.post(reverse("register"), self._data(phone="12345"))
        self.assertContains(response, "Kenyan phone number")
        self.assertFalse(User.objects.filter(username="newstudent").exists())

    def test_international_phone_format_is_accepted_and_tidied(self):
        self.client.post(reverse("register"), self._data(phone="+254 712-345 678"))
        self.assertEqual(StudentProfile.objects.get(user__username="newstudent").phone, "+254712345678")

    def test_too_short_id_is_rejected(self):
        response = self.client.post(reverse("register"), self._data(national_id="12"))
        self.assertContains(response, "valid ID or birth certificate number")


class ReviewPageDocumentsTests(TestCase):
    def test_committee_sees_a_private_link_to_each_document(self):
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        from .models import Document
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            admin_user = User.objects.create_superuser("boss", "boss@example.com", "pass12345")
            self.client.login(username="boss", password="pass12345")
            application = make_application(make_round(), make_student(1, "Nairobi"),
                                           Application.Status.SUBMITTED, 5000)
            page = self.client.get(reverse("admin:bursary_application_change", args=[application.pk]))
            self.assertContains(page, "No documents uploaded yet")
            doc = Document.objects.create(
                application=application, kind=Document.Kind.ID,
                file=SimpleUploadedFile("id.pdf", b"%PDF-1.4 test", content_type="application/pdf"))
            page = self.client.get(reverse("admin:bursary_application_change", args=[application.pk]))
            self.assertContains(page, reverse("download_document", args=[doc.pk]))


class ShowPasswordTests(TestCase):
    def test_login_page_has_the_show_password_button_script(self):
        self.assertContains(self.client.get(reverse("login")), "pw-toggle")
