"""Need scoring: turns an application's facts into a suggested score from 0 to 100.

This is a SUGGESTION to help the committee rank many applications quickly.
It never approves or rejects anyone: people decide, and the committee can
overrule the suggested score by entering their own "Need score".

The default weights below are only a starting point. Your committee should
agree its own criteria, then change them by adding a NEED_SCORING block to
config/settings.py (see the commented example there). Keep the weights adding
up to 100 so each line reads as "points out of its maximum".
"""
from django.conf import settings

DEFAULTS = {
    # Maximum points each factor can earn (these add up to 100).
    "weights": {
        "income": 40,        # lower family income = more points
        "orphan": 20,        # both parents deceased = full, one parent = half
        "dependants": 15,    # more siblings/dependants in school = more points
        "disability": 10,    # disability in the household
        "fee_balance": 15,   # larger share of the fees still unpaid = more points
    },
    # Annual family income (KES) at or below which income earns FULL points...
    "income_full_points_at_or_below": 100_000,
    # ...and at or above which it earns ZERO. In between it falls in a straight line.
    "income_zero_points_at_or_above": 600_000,
    # Number of dependants in school that earns full points.
    "dependants_for_full_points": 4,
}


def _config(override=None):
    config = {**DEFAULTS, "weights": dict(DEFAULTS["weights"])}
    custom = override if override is not None else (getattr(settings, "NEED_SCORING", None) or {})
    for key, value in custom.items():
        if key == "weights":
            config["weights"].update(value)
        else:
            config[key] = value
    return config


def compute_need_score(application, config=None):
    """Return (score, parts).

    score: whole number 0-100.
    parts: list of (label, points_earned, points_possible) for showing the working.
    """
    cfg = _config(config)
    weights = cfg["weights"]

    # Family income: straight line from full points (low income) to zero (high income).
    income = float(application.annual_family_income or 0)
    low = float(cfg["income_full_points_at_or_below"])
    high = float(cfg["income_zero_points_at_or_above"])
    if income <= low:
        income_factor = 1.0
    elif high <= low or income >= high:
        income_factor = 0.0
    else:
        income_factor = (high - income) / (high - low)

    # Parental status.
    orphan_factor = {"double": 1.0, "single": 0.5}.get(application.orphan_status, 0.0)

    # Dependants in school, capped.
    cap = max(1, int(cfg["dependants_for_full_points"]))
    dependants_factor = min((application.dependants_in_school or 0) / cap, 1.0)

    # Disability.
    disability_factor = 1.0 if application.has_disability else 0.0

    # Share of the year's fees that is still unpaid.
    total = float(application.total_fees or 0)
    balance = total - float(application.fees_paid or 0)
    fee_factor = max(0.0, min(balance / total, 1.0)) if total > 0 else 0.0

    factors = [
        ("income", "Family income", income_factor),
        ("orphan", "Parental status", orphan_factor),
        ("dependants", "Dependants in school", dependants_factor),
        ("disability", "Disability", disability_factor),
        ("fee_balance", "Unpaid fee balance", fee_factor),
    ]

    parts, earned, possible = [], 0.0, 0.0
    for key, label, factor in factors:
        weight = float(weights.get(key, 0))
        parts.append((label, round(factor * weight, 1), round(weight, 1)))
        earned += factor * weight
        possible += weight

    score = round(100 * earned / possible) if possible > 0 else 0
    return max(0, min(100, int(score))), parts
