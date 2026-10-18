from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from .scoring import compute_need_score


class BursaryRound(models.Model):
    """A funding window, e.g. "2026 Term 1 Bursary", with a budget and deadline."""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    max_award_per_student = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Optional cap on any single award (KES).",
    )
    opens_on = models.DateField()
    closes_on = models.DateField()
    is_active = models.BooleanField(default=True, help_text="Untick to hide this round completely.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-opens_on"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.opens_on and self.closes_on and self.closes_on < self.opens_on:
            raise ValidationError("Closing date cannot be before the opening date.")

    @property
    def is_open(self):
        today = timezone.localdate()
        return self.is_active and self.opens_on <= today <= self.closes_on

    @property
    def total_awarded(self):
        total = self.applications.filter(status=Application.Status.APPROVED).aggregate(
            t=Sum("amount_awarded")
        )["t"]
        return total or Decimal("0")

    @property
    def remaining_budget(self):
        return self.budget - self.total_awarded


class StudentProfile(models.Model):
    """Extra details about a student, linked to their login account."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=150)
    national_id = models.CharField("National ID / Birth certificate no.", max_length=20, unique=True)
    phone = models.CharField(max_length=20)
    county = models.CharField(max_length=80)
    ward = models.CharField(max_length=80, blank=True)
    institution = models.CharField("School / College / University", max_length=200)
    admission_number = models.CharField(max_length=50)
    course_or_form = models.CharField("Course or class/form", max_length=120)
    year_of_study = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return f"{self.full_name} ({self.admission_number})"


def document_upload_path(instance, filename):
    # Keep each student's documents under their own folder.
    return f"documents/user_{instance.application.student.user_id}/{filename}"


def validate_file_size(file):
    limit_mb = getattr(settings, "MAX_UPLOAD_MB", 5)
    if file.size > limit_mb * 1024 * 1024:
        raise ValidationError(f"File too large. Maximum size is {limit_mb} MB.")


class Application(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        WAITLISTED = "waitlisted", "Waitlisted"
        REJECTED = "rejected", "Rejected"

    class Orphan(models.TextChoices):
        NONE = "none", "Both parents alive"
        SINGLE = "single", "One parent deceased"
        DOUBLE = "double", "Both parents deceased"

    bursary_round = models.ForeignKey(BursaryRound, on_delete=models.PROTECT, related_name="applications")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="applications")

    # What the student provides
    annual_family_income = models.DecimalField("Annual family income (KES)", max_digits=12, decimal_places=2,
                                               validators=[MinValueValidator(0)])
    dependants_in_school = models.PositiveSmallIntegerField("Siblings/dependants currently in school", default=0)
    orphan_status = models.CharField(max_length=10, choices=Orphan.choices, default=Orphan.NONE)
    has_disability = models.BooleanField("Student or parent has a disability", default=False)
    total_fees = models.DecimalField("Total fees for the year (KES)", max_digits=10, decimal_places=2,
                                     validators=[MinValueValidator(0)])
    fees_paid = models.DecimalField("Fees already paid (KES)", max_digits=10, decimal_places=2, default=0,
                                    validators=[MinValueValidator(0)])
    amount_requested = models.DecimalField("Amount requested (KES)", max_digits=10, decimal_places=2,
                                           validators=[MinValueValidator(1)])
    reason = models.TextField("Why do you need this bursary?")

    # What the committee provides
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.SUBMITTED)
    need_score = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Committee score, 0-100.")
    suggested_score = models.PositiveSmallIntegerField(
        null=True, blank=True, editable=False,
        help_text="Automatic 0-100 suggestion from the application facts. Only a guide for the committee.")
    amount_awarded = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                         validators=[MinValueValidator(0)])
    committee_notes = models.TextField(blank=True, help_text="Visible to the student as feedback.")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="reviewed_applications")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["bursary_round", "student"], name="one_application_per_round"),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.bursary_round.name}"

    def save(self, *args, **kwargs):
        # Keep the automatic suggestion up to date whenever the whole record is saved.
        if kwargs.get("update_fields") is None:
            self.suggested_score = compute_need_score(self)[0]
        super().save(*args, **kwargs)

    @property
    def fee_balance(self):
        return self.total_fees - self.fees_paid

    def clean(self):
        if self.fees_paid is not None and self.total_fees is not None and self.fees_paid > self.total_fees:
            raise ValidationError("Fees paid cannot exceed total fees.")
        if self.status == self.Status.APPROVED:
            cap = self.bursary_round.max_award_per_student
            if cap is not None and self.amount_awarded > cap:
                raise ValidationError(f"Award exceeds the per-student cap of KES {cap}.")
            # Budget check: everything already approved in this round, excluding this application.
            others = self.bursary_round.applications.filter(status=self.Status.APPROVED).exclude(pk=self.pk)
            already = others.aggregate(t=Sum("amount_awarded"))["t"] or Decimal("0")
            if already + self.amount_awarded > self.bursary_round.budget:
                raise ValidationError(
                    f"Approving KES {self.amount_awarded} would exceed the round budget "
                    f"(KES {self.bursary_round.budget - already} remaining)."
                )
        elif self.amount_awarded and self.status != self.Status.APPROVED:
            raise ValidationError("Only approved applications can have an amount awarded. "
                                  "Set the amount to 0 or change the status to Approved.")


class Document(models.Model):
    class Kind(models.TextChoices):
        ID = "id", "ID / Birth certificate"
        FEE_STATEMENT = "fee_statement", "Fee statement / structure"
        ADMISSION = "admission", "Admission letter"
        INCOME = "income", "Proof of income / chief's letter"
        OTHER = "other", "Other"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    file = models.FileField(
        upload_to=document_upload_path,
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"]), validate_file_size],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_kind_display()} for {self.application}"
