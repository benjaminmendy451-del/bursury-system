from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ApplicationForm, DocumentForm, StudentRegistrationForm
from .models import Application, BursaryRound, Document, StudentProfile
from .notifications import notify_submitted

EDITABLE_STATUSES = (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW)


def home(request):
    rounds = [r for r in BursaryRound.objects.filter(is_active=True) if r.is_open]
    return render(request, "bursary/home.html", {"rounds": rounds})


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created. You can now apply for an open bursary.")
        return redirect("dashboard")
    return render(request, "registration/register.html", {"form": form})


def _get_profile(request):
    """Return the student's profile, or None for staff/committee accounts."""
    try:
        return request.user.profile
    except StudentProfile.DoesNotExist:
        return None


@login_required
def dashboard(request):
    profile = _get_profile(request)
    if profile is None:
        # Committee/staff members have no student profile; send them to the admin site.
        return redirect("admin:index")
    applications = profile.applications.select_related("bursary_round")
    open_rounds = [r for r in BursaryRound.objects.filter(is_active=True) if r.is_open]
    applied_ids = set(applications.values_list("bursary_round_id", flat=True))
    available = [r for r in open_rounds if r.id not in applied_ids]
    return render(request, "bursary/dashboard.html", {
        "profile": profile, "applications": applications, "available_rounds": available,
    })


@login_required
def apply(request, round_id):
    profile = _get_profile(request)
    if profile is None:
        messages.error(request, "Only student accounts can apply.")
        return redirect("dashboard")

    bursary_round = get_object_or_404(BursaryRound, pk=round_id, is_active=True)
    if not bursary_round.is_open:
        messages.error(request, "This bursary round is not currently open.")
        return redirect("home")
    if Application.objects.filter(bursary_round=bursary_round, student=profile).exists():
        messages.info(request, "You have already applied to this round.")
        return redirect("dashboard")

    form = ApplicationForm(request.POST or None, bursary_round=bursary_round)
    if request.method == "POST" and form.is_valid():
        application = form.save(commit=False)
        application.bursary_round = bursary_round
        application.student = profile
        try:
            application.save()
        except IntegrityError:
            messages.info(request, "You have already applied to this round.")
            return redirect("dashboard")
        notify_submitted(application)
        messages.success(request, "Application submitted. Now upload your supporting documents.")
        return redirect("application_detail", pk=application.pk)
    return render(request, "bursary/apply.html", {"form": form, "round": bursary_round})


@login_required
def application_detail(request, pk):
    profile = _get_profile(request)
    # A student can only ever see their own applications.
    application = get_object_or_404(Application, pk=pk, student=profile) if profile else None
    if application is None:
        raise Http404

    can_edit = application.status in EDITABLE_STATUSES
    doc_form = DocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if not can_edit:
            messages.error(request, "This application has been decided; documents can no longer be added.")
        elif doc_form.is_valid():
            doc = doc_form.save(commit=False)
            doc.application = application
            doc.save()
            messages.success(request, "Document uploaded.")
            return redirect("application_detail", pk=application.pk)
    return render(request, "bursary/application_detail.html", {
        "application": application, "doc_form": doc_form, "can_edit": can_edit,
    })


@login_required
def download_document(request, pk):
    """Documents hold personal data, so only the owner or committee staff may open them."""
    doc = get_object_or_404(Document.objects.select_related("application__student"), pk=pk)
    is_owner = doc.application.student.user_id == request.user.id
    if not (is_owner or request.user.is_staff):
        raise Http404
    return FileResponse(doc.file.open("rb"), as_attachment=False)
