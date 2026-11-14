# Putting BursaryNexa online (checklist)

Do these in order. Nothing here is needed to run the system on your own computer.

## 1. Remove the exposed email password
Go to https://myaccount.google.com/apppasswords, delete the old App password, create a new one,
and put it only in the hosting provider's settings (never in Git or in chat).

## 2. Create a real secret key
Run this once and copy the long result:

    python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"

## 3. Set these values at the host (not in Git)
    DJANGO_SECRET_KEY=<the long key from step 2>
    DJANGO_DEBUG=False
    DJANGO_ALLOWED_HOSTS=yourdomain.com
    DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com
    SITE_URL=https://yourdomain.com
    EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
    EMAIL_HOST_USER=...
    EMAIL_HOST_PASSWORD=<new App password>
    MYSQL_DB / MYSQL_USER / MYSQL_PASSWORD / MYSQL_HOST / MYSQL_PORT   (or the POSTGRES_* values)

With DJANGO_DEBUG=False the site refuses to start if DJANGO_SECRET_KEY is missing.

## 4. Install, build the static files, create the tables
    pip install -r requirements.txt
    python manage.py collectstatic --noinput
    python manage.py migrate
    python manage.py setup_committee
    python manage.py createsuperuser

## 5. Check the settings
    python manage.py check --deploy

Fix anything it lists, then run the site with a production server such as gunicorn
(`pip install gunicorn`, then `gunicorn config.wsgi`).

## 6. HTTPS
Hosts such as PythonAnywhere and Render give you HTTPS automatically. On your own server,
use Nginx with a free Let's Encrypt certificate. The settings already redirect to HTTPS
and mark cookies secure when DEBUG is off.

## 7. Documents and backups
Uploaded documents are private: they are never served from a public folder, only through the
login-protected page. They live in the `media` folder, which Git ignores, so back it up
yourself together with the database (`backup.ps1` on Windows, or `mysqldump` on a server).
Keep backups off GitHub.

## 8. Reminder emails (optional)
`python manage.py send_reminders` emails students about rounds that close in 3, 1 or 0 days:
those who have not applied yet, and those who applied but still have documents missing.
Because it only sends on those days, you can run it once a day without repeating the same
email. Try `python manage.py send_reminders --dry-run` first to see how many would go out.
On PythonAnywhere, use the Tasks tab to run it daily (the free plan allows one scheduled task),
for example: `/home/YOURNAME/.virtualenvs/bursary/bin/python /home/YOURNAME/bursury-system/manage.py send_reminders`.
Email must be set up first (see `.env.example`).
