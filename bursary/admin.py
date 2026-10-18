import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import Application, BursaryRound, Document, StudentProfile
from .notifications import notify_status_change
from .scoring import compute_need_score


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    readonly_fields = ("kind", "file", "uploaded_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BursaryRound)
class BursaryRoundAdmin(admin.ModelAdmin):
    list_display = ("name", "opens_on", "closes_on", "budget", "total_awarded", "remaining_budget", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "national_id", "institution", "county", "ward", "phone")
    search_fields = ("full_name", "national_id", "institution", "admission_number")
    list_filter = ("county",)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("student", "bursary_round", "status", "suggested_score", "need_score",
                    "amount_requested", "amount_awarded", "submitted_at")
    list_filter = ("status", "bursary_round", "orphan_status", "has_disability", "student__county")
    search_fields = ("student__full_name", "student__national_id", "student__institution")
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
            notify_status_change(application)
            count += 1
        self.message_user(request, f"{count} application(s) moved to Under review.", messages.SUCCESS)

    @admin.action(description="Reject selected (use with care)")
    def reject_selected(self, request, queryset):
        count = 0
        for application in queryset.exclude(status=Application.Status.APPROVED).select_related(
                "student__user", "bursary_round"):
            application.status = Application.Status.REJECTED
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
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
