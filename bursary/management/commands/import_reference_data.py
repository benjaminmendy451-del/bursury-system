import csv

from django.core.management.base import BaseCommand, CommandError

from bursary.counties import canonical_county
from bursary.models import Institution, Ward


class Command(BaseCommand):
    help = (
        "Load wards and institutions from CSV files so students pick from a dropdown.\n"
        "  --wards wards.csv          columns: county,ward\n"
        "  --institutions schools.csv column: name (one per row, header row 'name')\n"
        "Safe to run again: existing rows are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument("--wards")
        parser.add_argument("--institutions")
        parser.add_argument("--column", default="name",
                            help="Which column of the institutions file holds the school name (default: name).")

    def handle(self, *args, **options):
        if not options["wards"] and not options["institutions"]:
            raise CommandError("Give --wards and/or --institutions with a CSV file.")
        if options["wards"]:
            self._wards(options["wards"])
        if options["institutions"]:
            self._institutions(options["institutions"], options["column"].strip().lower())

    def _rows(self, path):
        try:
            with open(path, newline="", encoding="utf-8-sig") as handle:
                return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                        for row in csv.DictReader(handle)]
        except FileNotFoundError:
            raise CommandError(f"Cannot find {path}")

    def _wards(self, path):
        added = skipped = 0
        for number, row in enumerate(self._rows(path), start=2):
            county = canonical_county(row.get("county"))
            name = row.get("ward", "")
            if not county or not name:
                self.stdout.write(self.style.WARNING(f"Line {number}: skipped (county '{row.get('county')}', ward '{name}')"))
                skipped += 1
                continue
            _, created = Ward.objects.get_or_create(county=county, name=name)
            added += created
        self.stdout.write(self.style.SUCCESS(f"Wards: {added} added, {skipped} skipped."))

    def _institutions(self, path, column):
        added = skipped = 0
        rows = self._rows(path)
        if rows and column not in rows[0]:
            raise CommandError(f"No column called '{column}'. Columns found: {', '.join(rows[0])}. "
                               f"Use --column NAME to choose one.")
        for number, row in enumerate(rows, start=2):
            name = " ".join(row.get(column, "").split())
            if not name:
                skipped += 1
                continue
            _, created = Institution.objects.get_or_create(name=name)
            added += created
        self.stdout.write(self.style.SUCCESS(f"Institutions: {added} added, {skipped} skipped."))
