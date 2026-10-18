from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .counties import COUNTY_CHOICES
from .models import Application, Document, Institution, StudentProfile, Ward


class StudentRegistrationForm(UserCreationForm):
    """Creates the login account and the student profile in one step."""

    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    national_id = forms.CharField(max_length=20, label="National ID / Birth certificate no.")
    phone = forms.CharField(max_length=20)
    county = forms.ChoiceField(choices=COUNTY_CHOICES)
    ward = forms.CharField(max_length=80, required=False)
    institution = forms.CharField(max_length=200, label="School / College / University")
    institution_other = forms.CharField(
        max_length=200, required=False, label="Name of your school / college (only if not listed)")
    admission_number = forms.CharField(max_length=50)
    course_or_form = forms.CharField(max_length=120, label="Course or class/form")
    year_of_study = forms.IntegerField(min_value=1, max_value=10, initial=1)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    OTHER = "__other__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Wards: a dropdown grouped by county, once the committee has loaded the list.
        wards = {}
        for county, name in Ward.objects.values_list("county", "name"):
            wards.setdefault(county, []).append((name, name))
        self.has_ward_list = bool(wards)
        if wards:
            grouped = [(county, wards[county]) for county in sorted(wards)]
            self.fields["ward"] = forms.ChoiceField(
                choices=[("", "Select your ward")] + grouped, required=False)
        # Institutions: a dropdown plus "not listed", once the list is loaded.
        names = list(Institution.objects.values_list("name", flat=True))
        self.has_institution_list = bool(names)
        if names:
            self.fields["institution"] = forms.ChoiceField(
                label="School / College / University",
                choices=[("", "Select your school / college")] + [(n, n) for n in names]
                        + [(self.OTHER, "My school / college is not listed")])
        else:
            del self.fields["institution_other"]

    def clean(self):
        cleaned = super().clean()
        county, ward = cleaned.get("county"), cleaned.get("ward")
        if self.has_ward_list and ward and county:
            if not Ward.objects.filter(county=county, name=ward).exists():
                self.add_error("ward", "This ward is not in the county you selected.")
        if self.has_institution_list and cleaned.get("institution") == self.OTHER:
            other = (cleaned.get("institution_other") or "").strip()
            if not other:
                self.add_error("institution_other", "Please type the name of your school or college.")
            else:
                cleaned["institution"] = other
        return cleaned

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
