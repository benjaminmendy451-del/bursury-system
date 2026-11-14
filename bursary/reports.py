"""Numbers for the committee's reports page and CSV download."""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Lower, Trim

from .models import Application, BursaryRound

ZERO = Decimal("0")

# Colours for the status chart (the same family as the labels in the committee list).
STATUS_CHART_COLOURS = {
    Application.Status.SUBMITTED: "#98a2b3",
    Application.Status.UNDER_REVIEW: "#f2b705",
    Application.Status.APPROVED: "#1d7a43",
    Application.Status.WAITLISTED: "#3b6fd4",
    Application.Status.REJECTED: "#c0392b",
}
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


def build_charts(statuses, counties):
    """Data for the two charts on the reports page.

    statuses: list of (label, count) in the order of Application.Status.choices.
    counties: rows from breakdown().
    """
    total = sum(count for _, count in statuses)
    legend, stops, start = [], [], 0.0
    for (value, _), (label, count) in zip(Application.Status.choices, statuses):
        colour = STATUS_CHART_COLOURS[value]
        percent = count * 100 / total if total else 0.0
        legend.append({"label": label, "count": count, "colour": colour, "percent": round(percent)})
        if count:
            stops.append(f"{colour} {start:.2f}% {start + percent:.2f}%")
            start += percent
    gradient = f"conic-gradient({', '.join(stops)})" if stops else "conic-gradient(#e5ebe7 0 100%)"

    top = sorted(counties, key=lambda row: (-row["applications"], row["label"]))[:8]
    biggest = max((row["applications"] for row in top), default=0)
    bars = [{"label": row["label"], "count": row["applications"],
             "width": round(row["applications"] * 100 / biggest) if biggest else 0} for row in top]
    return {"total": total, "legend": legend, "gradient": gradient, "bars": bars}


def county_options():
    """County names for the filter box, grouped ignoring capital letters and extra spaces."""
    keys = (Application.objects.annotate(key=Lower(Trim("student__county")))
            .order_by().values_list("key", flat=True).distinct())
    return sorted({_label([key]) for key in keys if key and key.strip()})


def build_report(bursary_round=None, county="", status=""):
    """Everything the reports page shows. bursary_round=None means all rounds.

    county and status are optional extra filters. The budget figures always cover the
    whole round, because the money is shared by every county.
    """
    scope = Application.objects.all()
    if bursary_round is not None:
        scope = scope.filter(bursary_round=bursary_round)
    applications = scope
    county = (county or "").strip().lower()
    if county:
        applications = applications.annotate(
            filter_county=Lower(Trim("student__county"))).filter(filter_county=county)
    if status in dict(Application.Status.choices):
        applications = applications.filter(status=status)
    else:
        status = ""

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
    # Money already approved across the whole round (not only the filtered rows).
    spent = scope.aggregate(awarded=Sum("amount_awarded", filter=Q(status=APPROVED)))["awarded"] or ZERO
    percent_used = float(spent / budget * 100) if budget else 0.0

    return {
        "charts": build_charts(statuses, counties),
        "filtered": bool(county or status),
        "summary": {
            "applications": sum(count for _, count in statuses),
            "requested": sums["requested"] or ZERO,
            "awarded": awarded,
            "budget": budget,
            "spent": spent,
            "remaining": budget - spent,
            "percent_used": percent_used,
            "bar_width": max(0.0, min(percent_used, 100.0)),
        },
        "statuses": statuses,
        "counties": counties, "counties_total": totals(counties),
        "wards": wards, "wards_total": totals(wards),
        "institutions": institutions, "institutions_total": totals(institutions),
    }
