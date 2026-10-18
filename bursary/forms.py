from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .counties import COUNTY_CHOICES
from .models import Application, Document, StudentProfile


class StudentRegistrationForm(UserCreationForm):
    """Creates the login account and the student profile in one step."""

    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    national_id = forms.CharField(max_length=20, label="National ID / Birth certificate no.")
    phone = forms.CharField(max_length=20)
    county = forms.ChoiceField(choices=COUNTY_CHOICES)
    ward = forms.CharField(max_length=80, required=False)
    institution = forms.CharField(max_length=200, label="School / College / University")
    admission_number = forms.CharField(max_length=50)
    course_or_form = forms.CharField(max_length=120, label="Course or class/form")
    year_of_study = forms.IntegerField(min_value=1, max_value=10, initial=1)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_national_id(self):
        value = self.cleaned_data["national_id"].strip()
        if StudentProfile.objects.filter(national_id=value).exists():
            raise forms.ValidationError("An account with this ID already exists.")
        return value

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.save()
        StudentProfile.objects.create(
            user=user,
            full_name=self.cleaned_data["full_name"],
            national_id=self.cleaned_data["national_id"],
            phone=self.cleaned_data["phone"],
            county=self.cleaned_data["county"],
            ward=self.cleaned_data["ward"],
            institution=self.cleaned_data["institution"],
            admission_number=self.cleaned_data["admission_number"],
            course_or_form=self.cleaned_data["course_or_form"],
            year_of_study=self.cleaned_data["year_of_study"],
        )
        return user


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ("annual_family_income", "dependants_in_school", "orphan_status", "has_disability",
                  "total_fees", "fees_paid", "amount_requested", "reason")
        widgets = {"reason": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, bursary_round=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.bursary_round = bursary_round

    def clean(self):
        cleaned = super().clean()
        total, paid, requested = (cleaned.get("total_fees"), cleaned.get("fees_paid"),
                                  cleaned.get("amount_requested"))
        if total is not None and paid is not None and paid > total:
            raise forms.ValidationError("Fees paid cannot be more than total fees.")
        if total is not None and paid is not None and requested is not None and requested > (total - paid):
            self.add_error("amount_requested", "You cannot request more than your outstanding fee balance.")
        cap = self.bursary_round.max_award_per_student if self.bursary_round else None
        if cap is not None and requested is not None and requested > cap:
            self.add_error("amount_requested", f"The maximum award for this round is KES {cap}.")
        return cleaned


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ("kind", "file")
