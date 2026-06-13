"""Email delivery for the morning brief — Resend."""

from __future__ import annotations

import logging
import os
from datetime import date
from html import escape

from core.email_theme import render_email

log = logging.getLogger(__name__)

# When true, skip the actual API call and just log — useful for local dev.
_DRY_RUN = os.environ.get("RESEND_DRY_RUN", "false").lower() == "true"


def _send(
    html: str,
    subject: str,
    recipient: str,
    *,
    kind: str,
    reply_to: str | None = None,
) -> bool:
    """Deliver one HTML email via Resend. Returns True on success.

    ``reply_to`` sets the Reply-To header — used by issue reports so a reply lands
    in the reporter's inbox rather than the no-reply sender.
    """
    sender = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if _DRY_RUN:
        log.info("[dry-run] %s email to %s suppressed (subject: %s)", kind, recipient, subject)
        return True

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY environment variable is not set")

    import resend

    resend.api_key = os.environ["RESEND_API_KEY"]
    payload = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        result = resend.Emails.send(payload)
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


def send_issue_report(
    description: str, reporter_email: str, *, context: dict | None = None
) -> bool:
    """Email a user-submitted issue/feedback to the admin inbox.

    Recipient is ``ISSUE_REPORT_EMAIL`` (env). The user's text is HTML-escaped
    before embedding, Reply-To is the reporter so admins can respond directly,
    and ``context`` (extension version, username, …) is included for triage.
    """
    admin = os.environ.get("ISSUE_REPORT_EMAIL", "").strip()
    if not admin:
        log.error("ISSUE_REPORT_EMAIL not set — cannot deliver issue report")
        return False

    safe_desc = escape(description.strip()).replace("\n", "<br>")
    meta = ""
    if context:
        rows = "".join(
            f'<tr>'
            f'<td style="padding:4px 14px 4px 0;font-size:12px;text-transform:uppercase;'
            f'letter-spacing:.6px;color:#9a9a9a;white-space:nowrap;vertical-align:top">{escape(str(k))}</td>'
            f'<td style="padding:4px 0;font-size:13px;color:#3a3a3a">{escape(str(v))}</td>'
            f'</tr>'
            for k, v in context.items()
            if v
        )
        if rows:
            meta = (
                '<table cellpadding="0" cellspacing="0" '
                'style="margin-top:18px;border-top:1px solid #ececec;padding-top:14px;width:100%">'
                f"{rows}</table>"
            )

    body = f"""
<p style="margin:0 0 12px;font-size:13px;color:#9a9a9a">
  From <strong style="color:#3a3a3a">{escape(reporter_email)}</strong>
</p>
<div style="font-size:15px;line-height:1.6;color:#1a1a1a;white-space:pre-wrap">{safe_desc}</div>
{meta}"""

    html = render_email("New issue report", body, eyebrow="Issue report", with_quote=False)
    subject = f"OnTrack Brief — issue from {reporter_email}"
    return _send(html, subject, admin, kind="Issue", reply_to=reporter_email)
