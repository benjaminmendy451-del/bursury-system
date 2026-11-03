import csv

from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import Application, BursaryRound, Document, Institution, StudentProfile, Ward
from .notifications import notify_status_change
from .scoring import compute_need_score


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    readonly_fields = ("kind", "file", "uploaded_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ScoreBandFilter(admin.SimpleListFilter):
    """Filter by need score: the committee score if set, otherwise the automatic suggestion."""
    title = "need score"
    parameter_name = "band"

    def lookups(self, request, model_admin):
        return [("high", "High (70-100)"), ("medium", "Medium (40-69)"),
                ("low", "Low (0-39)"), ("unscored", "Not scored")]

    def queryset(self, request, queryset):
        value = self.value()
        if value not in ("high", "medium", "low", "unscored"):
            return queryset
        scored = queryset.annotate(band_score=Coalesce("need_score", "suggested_score"))
        if value == "high":
            return scored.filter(band_score__gte=70)
        if value == "medium":
            return scored.filter(band_score__gte=40, band_score__lt=70)
        if value == "low":
            return scored.filter(band_score__lt=40)
        return scored.filter(band_score__isnull=True)


@admin.register(BursaryRound)
class BursaryRoundAdmin(admin.ModelAdmin):
    list_display = ("name", "opens_on", "closes_on", "budget", "total_awarded", "remaining_budget", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "national_id", "institution", "county", "ward", "phone")
    search_fields = ("full_name", "national_id", "institution", "admission_number", "phone")
    list_filter = ("county",)
    list_per_page = 50


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("name", "county")
    list_filter = ("county",)
    search_fields = ("name", "county")
    list_per_page = 50


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("student", "bursary_round", "status", "suggested_score", "need_score",
                    "amount_requested", "amount_awarded", "submitted_at")
    list_filter = ("status", "bursary_round", ScoreBandFilter, "orphan_status", "has_disability",
                   "student__county")
    search_fields = ("student__full_name", "student__national_id", "student__institution",
                     "student__admission_number", "student__ward", "student__county", "student__phone")
    list_per_page = 50
    list_select_related = ("student", "bursary_round")
    date_hierarchy = "submitted_at"
    inlines = [DocumentInline]
    actions = ["mark_under_review", "reject_selected", "use_suggested_score", "recalculate_scores",
               "export_csv"]

    readonly_fields = ("student", "bursary_round", "annual_family_income", "dependants_in_school",
                       "orphan_status", "has_disability", "total_fees", "fees_paid", "amount_requested",
                       "reason", "submitted_at", "reviewed_by", "reviewed_at",
                       "suggested_score", "score_breakdown")

    fieldsets = (
        ("Applicant", {"fields": ("student", "bursary_round", "submitted_at")}),
        ("Student's submission", {"fields": ("annual_family_income", "dependants_in_school", "orphan_status",
                                              "has_disability", "total_fees", "fees_paid",
                                              "amount_requested", "reason")}),
        ("Committee decision", {"fields": ("suggested_score", "score_breakdown", "need_score", "status",
                                            "amount_awarded", "committee_notes",
                                            "reviewed_by", "reviewed_at")}),
    )

    @admin.display(description="How the suggestion was worked out")
    def score_breakdown(self, obj):
        if obj is None or obj.pk is None:
            return "-"
        score, parts = compute_need_score(obj)
        lines = format_html_join("", "<li>{}: <strong>{}</strong> / {}</li>", parts)
        return format_html(
            "<ul style='margin:0;padding-left:1.2em'>{}</ul>"
            "<p style='margin:6px 0 0'>Total: <strong>{}</strong> / 100. "
            "This is only a guide. The committee decides.</p>",
            lines, score)

    def save_model(self, request, obj, form, change):
        status_changed = "status" in form.changed_data
        award_changed = "amount_awarded" in form.changed_data
        # Stamp who made the decision and when.
        if status_changed or award_changed:
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)

        # Tell the student (email, plus SMS if configured) when the decision
        # changes, or when an approved amount is corrected.
        if status_changed or (award_changed and obj.status == Application.Status.APPROVED):
            notify_status_change(obj)

    @admin.action(description="Mark selected as Under review")
    def mark_under_review(self, request, queryset):
        count = 0
        for application in queryset.filter(status=Application.Status.SUBMITTED).select_related(
                "student__user", "bursary_round"):
            application.status = Application.Status.UNDER_REVIEW
            application.save(update_fields=["status", "updated_at"])
            self.log_change(request, application, "Status changed from Submitted to Under review (bulk action).")
            notify_status_change(application)
            count += 1
        self.message_user(request, f"{count} application(s) moved to Under review.", messages.SUCCESS)

    @admin.action(description="Reject selected (use with care)")
    def reject_selected(self, request, queryset):
        count = 0
        for application in queryset.exclude(status=Application.Status.APPROVED).select_related(
                "student__user", "bursary_round"):
            old_status = application.get_status_display()
            application.status = Application.Status.REJECTED
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
            self.log_change(request, application, f"Status changed from {old_status} to Rejected (bulk action).")
            notify_status_change(application)
            count += 1
        self.message_user(request, f"{count} application(s) rejected and applicants notified.",
                          messages.WARNING)

    @admin.action(description="Use the suggested score as the committee score (only where blank)")
    def use_suggested_score(self, request, queryset):
        count = 0
        for application in queryset.filter(need_score__isnull=True, suggested_score__isnull=False):
            application.need_score = application.suggested_score
            application.save(update_fields=["need_score", "updated_at"])
            self.log_change(request, application,
                            f"Need score set to {application.need_score} from the suggestion (bulk action).")
            count += 1
        self.message_user(request, f"Copied the suggested score into {count} application(s).",
                          messages.SUCCESS)

    @admin.action(description="Recalculate suggested scores")
    def recalculate_scores(self, request, queryset):
        applications = list(queryset)
        for application in applications:
            application.suggested_score = compute_need_score(application)[0]
        Application.objects.bulk_update(applications, ["suggested_score"])
        self.message_user(request, f"Recalculated {len(applications)} suggested score(s).",
                          messages.SUCCESS)

    @admin.action(description="Export selected to CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="applications.csv"'
        writer = csv.writer(response)
        writer.writerow(["Student", "National ID", "Institution", "County", "Ward", "Round", "Status",
                         "Requested (KES)", "Awarded (KES)", "Suggested score", "Need score", "Submitted"])
        for a in queryset.select_related("student", "bursary_round"):
            s = a.student
            writer.writerow([s.full_name, s.national_id, s.institution, s.county, s.ward,
                             a.bursary_round.name, a.get_status_display(), a.amount_requested,
                             a.amount_awarded, a.suggested_score if a.suggested_score is not None else "",
                             a.need_score if a.need_score is not None else "",
                             a.submitted_at.strftime("%Y-%m-%d")])
        return response


@admin.register(LogEntry)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only history of every change made in the committee site: who, when and what."""
    list_display = ("action_time", "user", "content_type", "object_repr", "what_changed")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")
    date_hierarchy = "action_time"
    list_per_page = 50

    @admin.display(description="What changed")
    def what_changed(self, obj):
        return obj.get_change_message()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
