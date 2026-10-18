# Bursary Management System

A Django web app where students apply for bursaries and a committee reviews, scores and approves them.

**Students can:** register, apply to an open bursary round, upload documents (ID, fee statement, admission letter, proof of income) and track the decision.

**The committee can** (in `/admin/`): create bursary rounds with a budget and deadline, review applications side by side with their documents, score need, approve with an amount (the system blocks awards that exceed the round budget or per-student cap), reject, and export to CSV.

## 1. Run it on your computer (VS Code)

Open this folder in VS Code (`File > Open Folder`), then open the terminal (`` Ctrl+` ``):

```bash
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Mac / Linux
pip install -r requirements.txt

python manage.py makemigrations bursary
python manage.py migrate
python manage.py setup_committee
python manage.py createsuperuser
python manage.py runserver
```

- Student site: http://127.0.0.1:8000/
- Committee/admin site: http://127.0.0.1:8000/admin/ (log in with the superuser you just created)

> `makemigrations bursary` is needed once because this starter ships without migration files. Commit the generated `bursary/migrations/0001_initial.py` to GitHub afterwards.

### First-time walkthrough

1. Log in at `/admin/`, open **Bursary rounds**, add one (opening date today or earlier, closing date in the future, a budget).
2. Open a private browser window, go to `/register/` and create a student account.
3. Apply for the round and upload a PDF or image.
4. Back in `/admin/` open **Applications**, review it, set the status to *Approved* with an amount, and save.
5. Refresh the student dashboard to see the decision.

### Adding committee members

In `/admin/` > **Users** > add user, tick **Staff status**, and put them in the **Committee** group (created by `setup_committee`). They can review applications but cannot delete data or manage users.

## 2. Put it on GitHub

```bash
git init
git add .
git commit -m "Initial bursary system"
git branch -M main
git remote add origin https://github.com/<your-username>/bursary-system.git
git push -u origin main
```

(Or use VS Code's **Source Control** panel: *Initialize Repository*, commit, then *Publish to GitHub*.)

Habits that will save you later:
- Work on a branch per feature (`git checkout -b feature/reports`), then open a Pull Request.
- `.gitignore` already excludes `db.sqlite3`, `media/` (student documents) and `.env`. Never commit those.

## 3. Deploy

On Render, Railway or PythonAnywhere, connect your GitHub repo and set the environment variables from `.env.example`. Before going live:

1. `DJANGO_DEBUG=False` and a long random `DJANGO_SECRET_KEY`.
2. Use PostgreSQL (set the `POSTGRES_*` variables, `pip install "psycopg[binary]"`).
3. Run `python manage.py collectstatic` and `python manage.py migrate` on the server.
4. Serve with gunicorn (`gunicorn config.wsgi`) behind HTTPS.
5. Uploaded documents are saved to `media/`. On hosts with temporary disks, switch to persistent storage (for example a mounted volume or private S3 bucket) or documents will be lost on redeploy.

## 4. Notifications (email and SMS)

Students are notified when:
- their application is received (the committee can also be emailed, see `COMMITTEE_EMAILS`)
- the committee marks it Under review, Approved, Waitlisted or Rejected, or corrects an approved amount

**Testing with no setup:** by default emails are printed in the terminal that runs `python manage.py runserver`. Register a student *with an email address*, apply, then approve in `/admin/` and watch the terminal.

**Real emails (Gmail example):** turn on 2-step verification, create an *App password*, and set the `EMAIL_*` variables from `.env.example`. In PowerShell, for the current terminal only:

```powershell
$env:EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
$env:EMAIL_HOST_USER="your.address@gmail.com"
$env:EMAIL_HOST_PASSWORD="your-app-password"
python manage.py runserver
```

**SMS:** create an Africa's Talking account, then set `AT_USERNAME` and `AT_API_KEY` (use `AT_USERNAME=sandbox` to test for free). SMS is skipped automatically while these are empty. Kenyan numbers such as `0712 345 678` are converted to `+254712345678`.

A failed email or SMS is logged but never stops an application from being saved. The code is in `bursary/notifications.py`.

## 5. Privacy

The system stores national IDs, phone numbers, family income and ID documents. In Kenya this falls under the Data Protection Act, 2019: collect only what you need, restrict access to the committee, keep the site on HTTPS, and register with the Office of the Data Protection Commissioner if your organisation is required to. Documents here are only served through a login-protected URL, not a public folder.

## 6. Project layout

```
config/            settings and root URLs
bursary/models.py  BursaryRound, StudentProfile, Application, Document
bursary/admin.py   committee review screen, bulk actions, CSV export
bursary/forms.py   registration + application forms with validation
bursary/views.py   student pages (home, register, dashboard, apply, detail, document download)
bursary/templates/ HTML pages
```

## 7. Good next steps

- Reports page with totals per round, county and ward
- Automatic need-scoring from income, orphan status and dependants
- Per-ward/county quotas and a reports page with totals
- Automated tests (`bursary/tests.py`) run by GitHub Actions on every push
