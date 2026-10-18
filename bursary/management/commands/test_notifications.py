"""Send a test email and/or SMS to check your settings.

    python manage.py test_notifications --email you@example.com
    python manage.py test_notifications --phone 0712345678
    python manage.py test_notifications --email you@example.com --phone 0712345678

Unlike the real notifications, this prints the exact reason when something
fails, so you can fix wrong passwords or settings quickly.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from bursary.notifications import normalize_phone, send_sms_detailed


class Command(BaseCommand):
    help = "Send a test email and/or SMS to check your notification settings."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Address to send a test email to.")
        parser.add_argument("--phone", help="Phone number to send a test SMS to, e.g. 0712345678.")

    def handle(self, *args, **options):
        email, phone = options["email"], options["phone"]
        if not email and not phone:
            raise CommandError("Give --email and/or --phone. Example: --email you@example.com")

        if email:
            self.stdout.write(f"\nEMAIL  backend: {settings.EMAIL_BACKEND}")
            if "console" in settings.EMAIL_BACKEND:
                self.stdout.write(self.style.WARNING(
                    "The console backend only PRINTS emails here. Set EMAIL_BACKEND to the SMTP "
                    "backend in your .env file to send real ones."))
            else:
                self.stdout.write(f"       sending from {settings.DEFAULT_FROM_EMAIL} via "
                                  f"{settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
            try:
                send_mail(
                    "Bursary system test email",
                    "If you can read this, your bursary system can send email.",
                    settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False,
                )
                self.stdout.write(self.style.SUCCESS(f"Email handed over for {email}. "
                                                     f"Check the inbox (and spam folder)."))
            except Exception as exc:  # show the real reason
                self.stdout.write(self.style.ERROR(f"Email FAILED: {exc}"))

        if phone:
            self.stdout.write(f"\nSMS    account: {settings.AT_USERNAME or '(not set)'}   "
                              f"number: {normalize_phone(phone)}")
            sent, detail = send_sms_detailed(phone, "Bursary system test: your SMS is working.")
            style = self.style.SUCCESS if sent else self.style.ERROR
            self.stdout.write(style(("SMS OK. " if sent else "SMS FAILED. ") + detail))
            if sent and settings.AT_USERNAME == "sandbox":
                self.stdout.write("Sandbox messages appear in the Africa's Talking simulator, "
                                  "not on a real phone.")
