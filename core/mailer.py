"""Email delivery for the morning brief — SendGrid."""

from __future__ import annotations

import logging
import os
from datetime import date

log = logging.getLogger(__name__)

_SANDBOX = os.environ.get("SENDGRID_SANDBOX", "false").lower() == "true"


def _client():
    from sendgrid import SendGridAPIClient
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY environment variable is not set")
    return SendGridAPIClient(api_key)


def _build_message(html: str, subject: str, recipient: str):
    from sendgrid.helpers.mail import Mail, MailSettings, SandBoxMode
    sender = os.environ.get("SENDGRID_FROM_EMAIL", "briefs@example.com")
    msg = Mail(
        from_email=sender,
        to_emails=recipient,
        subject=subject,
        html_content=html,
    )
    if _SANDBOX:
        settings = MailSettings()
        settings.sandbox_mode = SandBoxMode(enable=True)
        msg.mail_settings = settings
    return msg


def send_brief_to(html: str, recipient: str, today: date) -> bool:
    subject = f"OnTrack Brief \u2014 {today.strftime('%a %b %d')}"
    try:
        response = _client().send(_build_message(html, subject, recipient))
        log.info("Brief sent to %s (HTTP %s)", recipient, response.status_code)
        return True
    except Exception as exc:
        log.error("SendGrid failure sending brief to %s: %s", recipient, exc)
        return False


def send_reauth_email(recipient: str, app_url: str) -> bool:
    html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:560px;margin:32px auto;color:#333">
  <h2 style="color:#c0392b">&#x26A0; OnTrack Brief \u2014 Re-authentication needed</h2>
  <p>Your OnTrack session has expired. To continue receiving your daily briefs,
     open the <strong>OnTrack Brief</strong> Chrome extension and log into OnTrack — your token will refresh automatically.</p>
  <p style="color:#888;font-size:12px">Tip: you don&rsquo;t need to stay logged in to OnTrack &mdash;
     just don&rsquo;t click <em>Log Out</em>.</p>
</body></html>"""
    subject = "OnTrack Brief \u2014 Re-authentication needed"
    try:
        response = _client().send(_build_message(html, subject, recipient))
        log.info("Re-auth email sent to %s (HTTP %s)", recipient, response.status_code)
        return True
    except Exception as exc:
        log.error("SendGrid failure sending re-auth to %s: %s", recipient, exc)
        return False
