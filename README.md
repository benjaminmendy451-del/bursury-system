# BursaryNexa

BursaryNexa is a web-based bursary management system. Students register and apply for an open bursary round, upload supporting documents and are notified of the decision by email. The committee reviews applications with an automatic **need score**, approves awards within the round budget, and sees **reports by county, ward and school**.

Built with Django (Python). It runs on SQLite out of the box and can use MySQL or PostgreSQL.

## Features

**For students**
- Register with a county and ward chosen from dropdown lists, and a school, college or university chosen from a list (or typed in if not listed).
- Apply to any open bursary round, with checks on fees and the maximum award.
- Upload documents (PDF, JPG, PNG, up to 5 MB). Documents are only served through a login-protected link.
- Follow the status of each application and receive email notifications.

**For the committee** (the `/admin/` area)
- Create bursary rounds with a budget, a per-student cap and open and close dates.
- Review applications side by side with their documents, and see a **suggested need score** (0 to 100) with a line-by-line breakdown.
- Approve with an amount. The system blocks awards that exceed the round budget or the cap.
- Bulk actions: mark under review, reject, use the suggested score, recalculate scores, export to CSV.
- A **Reports** page: totals, budget used, applications by status, and tables by county, ward and school, with a CSV download. Students cannot open it.

**Notifications:** email (and optional SMS through Africa's Talking) when an application is received, goes under review, is approved, waitlisted or rejected.

<!--
Screenshots: save images in docs/screenshots and uncomment the lines below.
![Home](docs/screenshots/home.png)
![Application form](docs/screenshots/apply.png)
![Committee review](docs/screenshots/review.png)
![Reports](docs/screenshots/reports.png)
-->

## 1. Run it on your computer

Open the folder in VS Code (`File > Open Folder`), then open a terminal (`` Ctrl+` ``):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate         # Mac / Linux
pip install -r requirements.txt

python manage.py migrate
python manage.py setup_committee
python manage.py createsuperuser
python manage.py runserver
```

- Student site: http://127.0.0.1:8000/
- Committee site: http://127.0.0.1:8000/admin/ (log in with the superuser you created)

If the repository has no `bursary/migrations/` files yet, run `python manage.py makemigrations bursary` before `migrate`, and commit the generated files.

### Load the county, ward and school lists

Counties are built in. Wards and schools are loaded from CSV files so students pick from a list. Until you load them, the form accepts typed text.

```powershell
python manage.py import_reference_data --wards kenya-wards.csv --institutions kenya-universities.csv
```

- `--wards` expects columns `county,ward`. `--institutions` expects a column `name` (use `--column "School Name"` for a different column title).
- Running it again is safe; existing rows are skipped.
- Fix counties typed before the dropdown existed: `python manage.py tidy_counties`.
- Wards come from the IEBC county, constituency and ward listing (via the open-source `nicanor-korir/kenya-regions` dataset). The university list should be checked against the current CUE list.

### Use MySQL instead of SQLite

1. Create a database, for example `CREATE DATABASE bursary CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`.
2. `pip install mysqlclient`.
3. Add these lines to your `.env` file (see `.env.example`): `MYSQL_DB`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `MYSQL_PORT`.
4. Run `python manage.py migrate` and create the superuser again.

The MySQL tables (`bursary_application`, `bursary_studentprofile` and so on) can be read by MySQL Workbench or Power BI. Change a table's structure through `models.py` and `makemigrations`, not in Workbench.

### Adding committee members

In `/admin/` > **Users** > add user, tick **Staff status**, and put them in the **Committee** group (created by `setup_committee`). They can review applications and see reports but cannot delete data or manage users.

## 2. Notifications

By default, emails are printed in the terminal that runs `runserver`. For real email, create a file named `.env` next to `manage.py` and copy the *Notifications* section of `.env.example` into it. Use a Gmail address with a 16-letter App password (2-Step Verification is required), typed without spaces. `.env` is ignored by Git.

Check your settings:

```powershell
python manage.py test_notifications --email you@example.com
```

Notes:
- Real environment variables override `.env`. If email fails with an old password, check for leftover variables with `Get-ChildItem Env: | Where-Object Name -like 'EMAIL*'`.
- SMS is skipped while `AT_USERNAME` and `AT_API_KEY` are empty. Kenyan numbers like `0712 345 678` become `+254712345678`.
- A failed email or SMS is logged but never stops an application from being saved. See `bursary/notifications.py`.

## 3. Need scoring

Each application gets a suggested score from 0 to 100: family income (40), parental status (20), dependants in school (15), disability (10) and unpaid fee share (15). It is a guide only. The committee decides and can enter its own score. Students never see it.

Edit the `NEED_SCORING` block in `config/settings.py` to change the weights, then run `python manage.py rescore_applications`.

## 4. Tests

```powershell
python manage.py test
```

Covers the scoring rules, report totals, county and ward checks, and report access (anonymous visitors are redirected, students get 403, the committee gets the page and the CSV).

## 5. Scaling to a county (500,000+ applications)

The project runs well for a school or a class demo. A county-wide deployment needs these changes first:

| Area | Now | For a county |
|---|---|---|
| Database | SQLite or a single MySQL | PostgreSQL or managed MySQL with indexes and daily backups |
| Documents | Files on the server's disk | Private cloud storage (S3-type bucket) |
| Email and SMS | Gmail, sent while the user waits | A bulk email service and a background job queue |
| Servers | One development server | Several app servers behind a load balancer, HTTPS, `DEBUG=False` |
| Admin screens | Simple lists | Paging, search and filters tuned for large data |
| Testing | Unit tests | Load tests that simulate a rush near the deadline |

## 6. Privacy and security

The system stores national IDs, phone numbers, family income and ID documents. In Kenya this falls under the Data Protection Act, 2019: collect only what you need, restrict access to the committee, use HTTPS, and register with the Office of the Data Protection Commissioner when required.

- Never commit `.env`, `db.sqlite3`, `media/` or the virtual environment. `.gitignore` already excludes them.
- If a password or App password is ever shared by accident, delete it and create a new one.

## 7. Project layout

```
config/               settings and root URLs
bursary/models.py     BursaryRound, StudentProfile, Application, Document, Ward, Institution
bursary/admin.py      committee review screen, bulk actions, CSV export
bursary/scoring.py    suggested need score rules
bursary/reports.py    totals by county, ward and school
bursary/counties.py   the 47 counties
bursary/forms.py      registration and application forms with validation
bursary/views.py      student pages, document download, reports
bursary/notifications.py   email and SMS messages
bursary/management/commands/   setup_committee, import_reference_data, tidy_counties,
                               rescore_applications, test_notifications
bursary/templates/    HTML pages
```

## 8. Possible next steps

- Per-county or per-ward quotas
- A background job queue for notifications
- Student-facing explanation of why an application was waitlisted or rejected
- GitHub Actions to run `python manage.py test` on every push
