import csv
import os
from email.utils import parseaddr

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ApplicationForm, DocumentForm, StudentDetailsForm, StudentRegistrationForm
from .models import Application, BursaryRound, Document, StudentProfile
from .notifications import notify_submitted
from .reports import build_report, county_options

EDITABLE_STATUSES = (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW)


def _contact_email():
    """A real address for the help section: CONTACT_EMAIL, else the sender address; blank if unusable."""
    raw = os.environ.get("CONTACT_EMAIL") or settings.DEFAULT_FROM_EMAIL
    addr = parseaddr(raw)[1]
    domain = addr.rpartition("@")[2]
    return addr if "." in domain else ""


MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 5 * 60


def _login_key(request, username):
    return f"login-fail:{(username or '').strip().lower()}:{request.META.get('REMOTE_ADDR', '?')}"


class LockoutLoginView(LoginView):
    """Normal login, but five wrong passwords in a row lock that username for five minutes."""

    def post(self, request, *args, **kwargs):
        if cache.get(_login_key(request, request.POST.get("username")), 0) >= MAX_LOGIN_ATTEMPTS:
            form = self.get_form_class()(request=request)
            response = self.render_to_response(self.get_context_data(
                form=form, locked_message="Too many failed attempts. Please wait 5 minutes and try again."))
            response.status_code = 429
            return response
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = _login_key(self.request, form.data.get("username"))
        cache.set(key, cache.get(key, 0) + 1, LOCKOUT_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(_login_key(self.request, form.data.get("username")))
        return super().form_valid(form)


def home(request):
    rounds = [r for r in BursaryRound.objects.filter(is_active=True) if r.is_open]
    stats = {
        "open_rounds": len(rounds),
        "budget": sum(r.budget for r in rounds),
        "applications": Application.objects.count(),
    }
    return render(request, "bursary/home.html", {
        "rounds": rounds, "stats": stats if request.user.is_staff else None,
        "contact_email": _contact_email(),
    })


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
    applications = profile.applications.select_related("bursary_round").prefetch_related("documents")
    open_rounds = [r for r in BursaryRound.objects.filter(is_active=True) if r.is_open]
    applied_ids = set(applications.values_list("bursary_round_id", flat=True))
    available = [r for r in open_rounds if r.id not in applied_ids]
    page = Paginator(applications, 10).get_page(request.GET.get("page"))

    # Extra facts the dashboard shows for each application: progress step and missing documents.
    labels = dict(Document.Kind.choices)
    required = [k for k in labels if k != Document.Kind.OTHER]
    items = list(page.object_list)
    for a in items:
        have = {d.kind for d in a.documents.all()}
        a.step = {Application.Status.SUBMITTED: 1, Application.Status.UNDER_REVIEW: 2}.get(a.status, 3)
        a.missing_docs = ([labels[k] for k in required if k not in have]
                          if a.status in EDITABLE_STATUSES else [])
    page.object_list = items

    today = timezone.localdate()
    for r in available:
        r.days_left = (r.closes_on - today).days
    return render(request, "bursary/dashboard.html", {
        "profile": profile, "applications": page, "available_rounds": available,
    })


def _audit(request, obj, message):
    """Record a student's own edit in the same audit trail the committee uses."""
    LogEntry.objects.log_actions(request.user.pk, [obj], CHANGE, message)


@login_required
def edit_profile(request):
    profile = _get_profile(request)
    if profile is None:
        messages.error(request, "Only student accounts have details to edit.")
        return redirect("admin:index")
    if profile.applications.exclude(status__in=EDITABLE_STATUSES).exists():
        messages.error(request, "Your application has been decided, so your details are locked. "
                                "Please contact the bursary office to correct them.")
        return redirect("dashboard")
    form = StudentDetailsForm(request.POST or None, profile=profile)
    if request.method == "POST" and form.is_valid():
        changed = list(form.changed_data)
        if changed:
            form.save()
            _audit(request, profile, "Student edited their own details: " + ", ".join(changed) + ".")
            messages.success(request, "Your details have been updated.")
        else:
            messages.info(request, "No changes were made.")
        return redirect("dashboard")
    return render(request, "bursary/profile_edit.html", {"form": form})


@login_required
def edit_application(request, pk):
    profile = _get_profile(request)
    if profile is None:
        raise Http404
    application = get_object_or_404(Application, pk=pk, student=profile)
    if application.status != Application.Status.SUBMITTED:
        messages.error(request, "This application is already being reviewed or decided, "
                                "so it can no longer be changed.")
        return redirect("application_detail", pk=application.pk)
    form = ApplicationForm(request.POST or None, instance=application,
                           bursary_round=application.bursary_round)
    if request.method == "POST" and form.is_valid():
        changed = list(form.changed_data)
        if changed:
            form.save()
            _audit(request, application, "Student edited their application: " + ", ".join(changed) + ".")
            messages.success(request, "Your application has been updated.")
        else:
            messages.info(request, "No changes were made.")
        return redirect("application_detail", pk=application.pk)
    return render(request, "bursary/application_edit.html", {"form": form, "application": application})


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
def award_letter(request, pk):
    """A printable award letter. Only for approved applications; the owner or committee may open it."""
    application = get_object_or_404(Application.objects.select_related("student", "bursary_round"), pk=pk)
    is_owner = application.student.user_id == request.user.id
    if not (is_owner or request.user.has_perm("bursary.view_application")):
        raise Http404
    if application.status != Application.Status.APPROVED:
        raise Http404
    return render(request, "bursary/award_letter.html", {
        "application": application, "issued_on": timezone.localdate(),
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


def _report_filters(request):
    """The optional county and status filters from the page address. Returns (county, status)."""
    county = request.GET.get("county", "").strip()[:80]
    status = request.GET.get("status", "")
    if status not in dict(Application.Status.choices):
        status = ""
    return county, status


@login_required
@permission_required("bursary.view_application", raise_exception=True)
def reports(request):
    """Totals for the committee. Students do not have this permission, so they get a 403."""
    rounds, selected_round, round_param = _report_scope(request)
    county, status = _report_filters(request)
    return render(request, "bursary/reports.html", {
        "rounds": rounds, "selected_round": selected_round, "round_param": round_param,
        "county": county, "status": status,
        "county_options": county_options(), "status_choices": Application.Status.choices,
        "report": build_report(selected_round, county, status),
    })


@login_required
@permission_required("bursary.view_application", raise_exception=True)
def reports_csv(request):
    _, selected_round, _ = _report_scope(request)
    county, status = _report_filters(request)
    report = build_report(selected_round, county, status)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bursary-report.csv"'
    writer = csv.writer(response)
    writer.writerow(["Bursary report", selected_round.name if selected_round else "All rounds"])
    if report["filtered"]:
        writer.writerow(["Filters", f"County: {county or 'all'}",
                         f"Status: {dict(Application.Status.choices).get(status, 'all')}"])
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


@login_required
@permission_required("bursary.view_application", raise_exception=True)
def analytics(request):
    """Committee-only page that shows the Power BI report inside the site."""
    url = settings.POWERBI_EMBED_URL
    if not url.startswith("https://"):
        url = ""  # only ever embed secure addresses
    return render(request, "bursary/analytics.html", {"embed_url": url})
