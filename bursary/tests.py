"""Checks for the need-scoring rules. Run with:  python manage.py test

These pass the default weights explicitly, so they keep working even if you
later customise NEED_SCORING in settings.
"""
import unittest
from types import SimpleNamespace

from bursary.scoring import DEFAULTS, compute_need_score


def make_application(**overrides):
    values = dict(annual_family_income=0, dependants_in_school=0, orphan_status="none",
                  has_disability=False, total_fees=100000, fees_paid=0)
    values.update(overrides)
    return SimpleNamespace(**values)


def score(**overrides):
    return compute_need_score(make_application(**overrides), DEFAULTS)[0]


class NeedScoreTests(unittest.TestCase):
    def test_most_needy_application_scores_100(self):
        self.assertEqual(score(annual_family_income=0, orphan_status="double",
                               dependants_in_school=6, has_disability=True), 100)

    def test_least_needy_application_scores_0(self):
        self.assertEqual(score(annual_family_income=900000, fees_paid=100000), 0)

    def test_income_falls_in_a_straight_line(self):
        # Midway between 100,000 and 600,000 earns half of 40 points, plus 15 for unpaid fees.
        self.assertEqual(score(annual_family_income=350000), 35)

    def test_one_deceased_parent_earns_half_the_orphan_points(self):
        self.assertEqual(score(annual_family_income=350000, orphan_status="single"), 45)

    def test_disability_adds_points(self):
        self.assertEqual(score(annual_family_income=350000, has_disability=True), 45)

    def test_zero_fees_does_not_crash(self):
        self.assertGreaterEqual(score(total_fees=0), 0)

    def test_all_zero_weights_score_zero(self):
        zero = {"weights": {key: 0 for key in DEFAULTS["weights"]}}
        self.assertEqual(compute_need_score(make_application(), zero)[0], 0)

    def test_breakdown_lists_five_factors(self):
        _, parts = compute_need_score(make_application(annual_family_income=350000), DEFAULTS)
        self.assertEqual(len(parts), 5)


if __name__ == "__main__":
    unittest.main()
