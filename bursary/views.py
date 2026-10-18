import csv

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ApplicationForm, DocumentForm, StudentRegistrationForm
from .models import Application, BursaryRound, Document, StudentProfile
from .notifications import notify_submitted
from .reports import build_report

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


# --- Committee reports -------------------------------------------------------
def _report_scope(request):
    """Which round the report covers. Returns (all_rounds, selected_round_or_None, round_param)."""
    rounds = list(BursaryRound.objects.all())  # newest first
    raw = request.GET.get("round", "")
    if raw == "all":
        return rounds, None, "all"
    if raw.isdigit():
        for bursary_round in rounds:
            if bursary_round.pk == int(raw):
                return rounds, bursary_round, str(bursary_round.pk)
    if rounds:
        return rounds, rounds[0], str(rounds[0].pk)
    return rounds, None, "all"


@login_required
@permission_required("bursary.view_application", raise_exception=True)
def reports(request):
    """Totals for the committee. Students do not have this permission, so they get a 403."""
    rounds, selected_round, round_param = _report_scope(request)
    return render(request, "bursary/reports.html", {
        "rounds": rounds, "selected_round": selected_round, "round_param": round_param,
        "report": build_report(selected_round),
    })


@login_required
@permission_required("bursary.view_application", raise_exception=True)
def reports_csv(request):
    _, selected_round, _ = _report_scope(request)
    report = build_report(selected_round)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bursary-report.csv"'
    writer = csv.writer(response)
    writer.writerow(["Bursary report", selected_round.name if selected_round else "All rounds"])
    summary = report["summary"]
    writer.writerow(["Applications", summary["applications"]])
    writer.writerow(["Requested (KES)", summary["requested"]])
    writer.writerow(["Awarded (KES)", summary["awarded"]])
    writer.writerow(["Budget (KES)", summary["budget"]])
    writer.writerow(["Budget remaining (KES)", summary["remaining"]])

    sections = [
        ("By county", "County", report["counties"], report["counties_total"]),
        ("By ward", "County, ward", report["wards"], report["wards_total"]),
        ("By institution", "Institution", report["institutions"], report["institutions_total"]),
    ]
    for title, first_column, rows, total in sections:
        writer.writerow([])
        writer.writerow([title])
        writer.writerow([first_column, "Applications", "Approved", "Requested (KES)", "Awarded (KES)"])
        for row in rows:
            writer.writerow([row["label"], row["applications"], row["approved"],
                             row["requested"], row["awarded"]])
        writer.writerow(["Total", total["applications"], total["approved"],
                         total["requested"], total["awarded"]])
    return response
