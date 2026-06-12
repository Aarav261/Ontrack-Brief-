"""Email delivery for the morning brief — Resend."""

from __future__ import annotations

import logging
import os
from datetime import date

log = logging.getLogger(__name__)

# When true, skip the actual API call and just log — useful for local dev.
_DRY_RUN = os.environ.get("RESEND_DRY_RUN", "false").lower() == "true"


def _send(html: str, subject: str, recipient: str, *, kind: str) -> bool:
    """Deliver one HTML email via Resend. Returns True on success."""
    sender = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if _DRY_RUN:
        log.info("[dry-run] %s email to %s suppressed (subject: %s)", kind, recipient, subject)
        return True

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY environment variable is not set")

    import resend

    resend.api_key = os.environ["RESEND_API_KEY"]
    try:
        result = resend.Emails.send(
            {
                "from": sender,
                "to": [recipient],
                "subject": subject,
                "html": html,
            }
        )
        log.info("%s email sent to %s (id %s)", kind, recipient, result.get("id"))
        return True
    except Exception as exc:
        log.error("Resend failure sending %s to %s: %s", kind, recipient, exc)
        return False


def send_brief_to(html: str, recipient: str, today: date, due_this_week: int) -> bool:
    task_label = "task" if due_this_week == 1 else "tasks"
    subject = f"{due_this_week} {task_label} due this week — OnTrack Brief"
    return _send(html, subject, recipient, kind="Brief")


def send_reauth_email(recipient: str, app_url: str) -> bool:
    html = """<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:560px;margin:32px auto;color:#333">
  <h2 style="color:#c0392b">&#x26A0; OnTrack Brief — Re-authentication needed</h2>
  <p>Your OnTrack session has expired. To continue receiving your daily briefs,
     open the <strong>OnTrack Brief</strong> Chrome extension and log into OnTrack —
     your token will refresh automatically.</p>
  <p style="color:#888;font-size:12px">Tip: you don&rsquo;t need to stay logged in to
     OnTrack &mdash; just don&rsquo;t click <em>Log Out</em>.</p>
</body></html>"""
    subject = "OnTrack Brief — Re-authentication needed"
    return _send(html, subject, recipient, kind="Re-auth")
