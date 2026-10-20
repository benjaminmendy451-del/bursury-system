"""Email and SMS notifications.

Students are told when their application is received and when the committee
makes a decision. Committee members can optionally be emailed about new
applications (set COMMITTEE_EMAILS).

A failure to send (no internet, wrong password, SMS credit finished) is logged
but never stops an application from being saved.

Email: works out of the box. By default emails are printed in the terminal
running `runserver`, so you can test with no setup. Set the EMAIL_* variables
(see .env.example) to send real emails.

SMS: uses Africa's Talking. Switched on only when AT_USERNAME and AT_API_KEY
are set; otherwise SMS is silently skipped.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

from .models import Application

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Low-level senders
# --------------------------------------------------------------------------
def normalize_phone(raw):
    """Turn 0712 345 678 / 254712345678 / 712345678 into +254712345678."""
    number = "".join(ch for ch in (raw or "") if ch.isdigit() or ch == "+")
    if number.startswith("+"):
        return number
    if number.startswith("254"):
        return "+" + number
    if number.startswith("0"):
        return "+254" + number[1:]
    if len(number) == 9 and number[0] in "71":
        return "+254" + number
    return number


def send_email(to_addresses, subject, body):
    to_addresses = [a for a in to_addresses if a]
    if not to_addresses:
        return False
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, to_addresses, fail_silently=False)
        return True
    except Exception:  # never let a mail problem block saving
        logger.exception("Could not send email to %s", to_addresses)
        return False


def send_sms_detailed(phone, message):
    """Send an SMS through Africa's Talking. Returns (sent, explanation)."""
    if not getattr(settings, "SMS_ENABLED", False):
        return False, "SMS is switched off (AT_USERNAME and AT_API_KEY are not set)."
    to = normalize_phone(phone)
    if not to.startswith("+"):
        return False, f"'{phone}' is not a usable phone number."

    host = "api.sandbox.africastalking.com" if settings.AT_USERNAME == "sandbox" else "api.africastalking.com"
    payload = {"username": settings.AT_USERNAME, "to": to, "message": message}
    if settings.AT_SENDER_ID:
        payload["from"] = settings.AT_SENDER_ID
    request = urllib.request.Request(
        f"https://{host}/version1/messaging",
        data=urllib.parse.urlencode(payload).encode(),
        headers={
            "apiKey": settings.AT_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        return False, f"Africa's Talking rejected the request (HTTP {exc.code}): {body}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"Could not reach Africa's Talking: {exc}"

    try:
        data = json.loads(raw)["SMSMessageData"]
    except (ValueError, KeyError, TypeError):
        return False, f"Unexpected reply from Africa's Talking: {raw[:300]}"
    recipients = data.get("Recipients") or []
    if recipients and recipients[0].get("status") == "Success":
        return True, "Accepted by Africa's Talking."
    status = recipients[0].get("status") if recipients else data.get("Message", "unknown")
    return False, f"Africa's Talking said: {status}"


def send_sms(phone, message):
    """Send an SMS if SMS is configured. Failures are logged, never raised."""
    if not getattr(settings, "SMS_ENABLED", False):
        return False
    sent, detail = send_sms_detailed(phone, message)
    if not sent:
        logger.warning("SMS to %s was not sent: %s", phone, detail)
    return sent


# --------------------------------------------------------------------------
# Message wording
# --------------------------------------------------------------------------
def _application_url(application):
    return f"{settings.SITE_URL.rstrip('/')}/applications/{application.pk}/"


def _status_content(application):
    """Return (email subject, email lines, short SMS text) for the current status."""
    round_name = application.bursary_round.name
    status = application.status
    S = Application.Status

    if status == S.APPROVED:
        amount = application.amount_awarded
        return (
            f"Bursary approved: {round_name}",
            [f"Congratulations! Your application for {round_name} has been APPROVED.",
             f"Amount awarded: KES {amount:,.2f}"],
            f"BursaryNexa: your application for {round_name} is APPROVED. KES {amount:,.0f} awarded. "
            f"Log in for details.",
        )
    if status == S.REJECTED:
        return (
            f"Bursary decision: {round_name}",
            [f"Thank you for applying for {round_name}. After careful review, we are sorry to say "
             f"your application was not successful this time."],
            f"BursaryNexa: your application for {round_name} was not successful this time. "
            f"Log in for feedback.",
        )
    if status == S.WAITLISTED:
        return (
            f"Bursary update: {round_name}",
            [f"Your application for {round_name} has been placed on the WAITLIST. "
             f"We will contact you if funds become available."],
            f"BursaryNexa: your application for {round_name} is on the waitlist. "
            f"We will contact you if funds become available.",
        )
    # Under review
    return (
        f"Bursary update: {round_name}",
        [f"Your application for {round_name} is now UNDER REVIEW by the committee."],
        f"BursaryNexa: your application for {round_name} is now under review.",
    )


# --------------------------------------------------------------------------
# Public functions (called from views.py and admin.py)
# --------------------------------------------------------------------------
def notify_submitted(application):
    """Tell the student we received the application; alert the committee."""
    student = application.student
    round_name = application.bursary_round.name

    body = (
        f"Hello {student.full_name},\n\n"
        f"We have received your application for {round_name}.\n"
        f"Reference number: #{application.pk}\n"
        f"Amount requested: KES {application.amount_requested:,.2f}\n\n"
        f"Please make sure you have uploaded your supporting documents. "
        f"You can follow the progress here:\n{_application_url(application)}\n\n"
        f"BursaryNexa Committee"
    )
    send_email([student.user.email], f"Application received: {round_name}", body)
    send_sms(student.phone,
             f"BursaryNexa: we received your application for {round_name}. Ref #{application.pk}.")

    committee = getattr(settings, "COMMITTEE_EMAILS", [])
    if committee:
        send_email(
            committee,
            f"New bursary application: {student.full_name}",
            f"{student.full_name} ({student.institution}) applied for {round_name}, "
            f"requesting KES {application.amount_requested:,.2f}.\n\n"
            f"Review it in the committee area: {settings.SITE_URL.rstrip('/')}/admin/bursary/application/"
            f"{application.pk}/change/",
        )


def notify_status_change(application):
    """Tell the student about the committee's decision. Does nothing for 'submitted'."""
    if application.status == Application.Status.SUBMITTED:
        return

    student = application.student
    subject, lines, sms_text = _status_content(application)

    body = f"Hello {student.full_name},\n\n" + "\n".join(lines) + "\n"
    if application.committee_notes:
        body += f"\nMessage from the committee:\n{application.committee_notes}\n"
    body += f"\nView your application:\n{_application_url(application)}\n\nBursaryNexa Committee"

    send_email([student.user.email], subject, body)
    send_sms(student.phone, sms_text)
