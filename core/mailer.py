"""Email delivery for the morning brief — Resend."""

from __future__ import annotations

import logging
import os
from datetime import date

from core.email_theme import render_email

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


def send_briefs_enabled_email(recipient: str) -> bool:
    """Confirm briefs are on when the user enables them but has no active units.

    Sent only on an explicit enable (not the daily cron), so the user gets
    feedback instead of silence when there's currently nothing to brief.
    """
    body = """
<p style="margin:0;font-size:15px;line-height:1.65;color:#3a3a3a">
  Your OnTrack Brief is enabled. You don&rsquo;t have any active units right now,
  so there&rsquo;s nothing to brief yet &mdash; you&rsquo;ll start getting a brief each
  weekday morning once a new trimester begins.
</p>"""
    html = render_email("You're all set", body)
    subject = "OnTrack Brief enabled"
    return _send(html, subject, recipient, kind="Briefs-enabled")


def send_reauth_email(recipient: str, app_url: str) -> bool:
    body = """
<p style="margin:0 0 14px;font-size:15px;line-height:1.65;color:#3a3a3a">
  Your OnTrack session has expired. To keep receiving your daily briefs, open the
  <strong>OnTrack Brief</strong> Chrome extension and log into OnTrack &mdash; your
  session refreshes automatically.
</p>
<p style="margin:0;font-size:13px;line-height:1.6;color:#9a9a9a">
  You don&rsquo;t need to stay logged in to OnTrack &mdash; just don&rsquo;t click
  <em>Log Out</em>.
</p>"""
    html = render_email("Re-authentication needed", body)
    subject = "OnTrack Brief — Re-authentication needed"
    return _send(html, subject, recipient, kind="Re-auth")
