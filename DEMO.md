# BursaryNexa demo script (about 8 minutes)

## Before you start (10 minutes earlier)

- [ ] Open VS Code in the project folder, open a terminal, and check that `(.venv)` shows at the start of the line.
- [ ] MySQL is running (Windows Services > MySQL80 > Running) if you use MySQL.
- [ ] Start the site: `python manage.py runserver`. Keep that terminal open.
- [ ] In the browser, open the home page (http://127.0.0.1:8000/), a private window for the student, and `/admin/` in another tab.
- [ ] One bursary round exists, is active, and is open today.
- [ ] Wards and schools are loaded (`import_reference_data`).
- [ ] Email works: `python manage.py test_notifications --email your@address.com`.
- [ ] A second student with a different county has an application already, so the reports have more than one row.
- [ ] **Backup plan:** if email fails, delete the `EMAIL_BACKEND` line in `.env` and restart. Emails then print in the terminal. Say so openly and show them there.

## The story

**1. The problem (30 seconds)**
Bursary applications are often on paper: slow, easy to lose, hard to compare fairly, and impossible to total by area. BursaryNexa moves the process online.

**2. A student registers (1.5 minutes) - private window**
- Click Register. Show that **County and Ward are dropdowns**, and the school is a list with a "not listed" option. Point out that this keeps the data clean, so reports are accurate.
- Fill in the form, including a real email address you can open, and submit.

**3. The student applies (1.5 minutes)**
- Click Apply on the open round. Fill in income, dependants, fees and the amount requested.
- Show a validation: ask for more than the fee balance and show the error.
- Submit, then upload a PDF or image. Mention documents are only served to the owner and the committee.
- Show the "application received" email (inbox or terminal).

**4. The committee reviews (2 minutes) - /admin/ tab**
- Open **Applications**. Show the **suggested need score** column and click it to rank.
- Open the application: show the documents and the **score breakdown** (income, parental status, dependants, disability, unpaid fees).
- Say clearly: **the score is a guide, a person decides.** The committee can enter its own score.
- Set the status to **Approved** with an amount and save. Show that an amount over the cap or the budget is blocked.

**5. The student is notified (45 seconds)**
- Show the approval email, signed "BursaryNexa Committee". Back in the student window, refresh the dashboard to show the new status.

**6. Reports (1.5 minutes)**
- Click **Reports** in the top bar. Show the totals, the budget bar, applications by status, and the county, ward and school tables.
- Switch the round, then click **Download CSV** and open it.
- Show that a student cannot open `/reports/` (403 in the private window).

**7. Power BI (optional, 1 minute)**
- Show the dashboard connected to the MySQL database: awarded amount by county, applications by status.

**8. Close (30 seconds)**
Summarise: online applications, fair and consistent scoring, instant notifications, and live reports. Next steps: county scale (cloud storage, job queue, load testing) and data protection compliance.

## Questions you may be asked

- **Is the score fair?** It is a transparent starting point (weights shown in `scoring.py` and `settings.py`). A person can override it, and students do not see it.
- **How do you protect personal data?** Login required, documents only through a protected link, committee-only reports, secrets in `.env` never on GitHub, Data Protection Act 2019 compliance as a requirement before launch.
- **Could it handle a whole county?** Not as it is. It needs PostgreSQL, cloud file storage, a bulk email service, a job queue and load tests (see the table in the README).
- **What if two students share a name or ID?** National ID is unique, and a student can apply only once per round.
- **Why Django?** Built-in authentication, admin screen and database tools, so security basics are handled by a mature framework.
