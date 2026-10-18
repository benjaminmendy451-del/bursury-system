"""Numbers for the committee's reports page and CSV download."""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Lower, Trim

from .models import Application, BursaryRound

ZERO = Decimal("0")
APPROVED = Application.Status.APPROVED


def _label(parts):
    """'  nairobi ' + 'KILELESHWA' -> 'Nairobi, Kileleshwa'. Empty -> '(not given)'."""
    cleaned = [part.strip().title() for part in parts if part and part.strip()]
    return ", ".join(cleaned) if cleaned else "(not given)"


def breakdown(queryset, fields):
    """Group applications by the given fields, ignoring capital letters and extra spaces.

    fields: {"name_for_this_column": "student__county", ...}
    Returns a list of rows: label, applications, approved, requested, awarded.
    """
    keys = list(fields)
    rows = (
        queryset
        .annotate(**{key: Lower(Trim(path)) for key, path in fields.items()})
        .values(*keys)
        .annotate(
            applications=Count("id"),
            approved=Count("id", filter=Q(status=APPROVED)),
            requested=Sum("amount_requested"),
            awarded=Sum("amount_awarded", filter=Q(status=APPROVED)),
        )
        .order_by(*keys)
    )
    return [
        {
            "label": _label([row[key] for key in keys]),
            "applications": row["applications"],
            "approved": row["approved"],
            "requested": row["requested"] or ZERO,
            "awarded": row["awarded"] or ZERO,
        }
        for row in rows
    ]


def totals(rows):
    return {
        "applications": sum(row["applications"] for row in rows),
        "approved": sum(row["approved"] for row in rows),
        "requested": sum((row["requested"] for row in rows), ZERO),
        "awarded": sum((row["awarded"] for row in rows), ZERO),
    }


def build_report(bursary_round=None):
    """Everything the reports page shows. bursary_round=None means all rounds."""
    applications = Application.objects.all()
    if bursary_round is not None:
        applications = applications.filter(bursary_round=bursary_round)

    counties = breakdown(applications, {"county_key": "student__county"})
    wards = breakdown(applications, {"county_key": "student__county", "ward_key": "student__ward"})
    institutions = sorted(
        breakdown(applications, {"institution_key": "student__institution"}),
        key=lambda row: (-row["applications"], row["label"]),
    )

    status_counts = {
        row["status"]: row["n"]
        for row in applications.order_by().values("status").annotate(n=Count("id"))
    }
    statuses = [(label, status_counts.get(value, 0)) for value, label in Application.Status.choices]

    sums = applications.aggregate(
        requested=Sum("amount_requested"),
        awarded=Sum("amount_awarded", filter=Q(status=APPROVED)),
    )
    if bursary_round is not None:
        budget = bursary_round.budget
    else:
        budget = BursaryRound.objects.aggregate(total=Sum("budget"))["total"] or ZERO
    awarded = sums["awarded"] or ZERO
    percent_used = float(awarded / budget * 100) if budget else 0.0

    return {
        "summary": {
            "applications": sum(count for _, count in statuses),
            "requested": sums["requested"] or ZERO,
            "awarded": awarded,
            "budget": budget,
            "remaining": budget - awarded,
            "percent_used": percent_used,
            "bar_width": max(0.0, min(percent_used, 100.0)),
        },
        "statuses": statuses,
        "counties": counties, "counties_total": totals(counties),
        "wards": wards, "wards_total": totals(wards),
        "institutions": institutions, "institutions_total": totals(institutions),
    }
