"""Email delivery for the morning brief."""

from __future__ import annotations

import configparser
import logging
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


def send_email(html: str, cfg: configparser.ConfigParser, today: date) -> bool:
    sender    = cfg["email"]["sender"]
    recipient = cfg["email"]["recipient"]
    password  = cfg["email"]["app_password"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📚 OnTrack Brief — {today.strftime('%a %b %d')}"
    msg["From"]    = f"OnTrack Brief <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())
        log.info("Brief sent to %s", recipient)
        return True
    except Exception as exc:
        log.error("SMTP failure sending to %s: %s", recipient, exc)
        return False


def send_reauth_email(recipient: str, app_url: str, cfg: configparser.ConfigParser) -> bool:
    """Notify a subscriber that their OnTrack token expired and they need to re-subscribe."""
    try:
        sender   = os.environ.get("SMTP_SENDER")   or cfg["email"]["sender"]
        password = os.environ.get("SMTP_PASSWORD") or cfg["email"]["app_password"]
    except KeyError as exc:
        log.error("Missing SMTP config key: %s", exc)
        return False

    html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:560px;margin:32px auto;color:#333">
  <h2 style="color:#c0392b">&#x26A0; OnTrack Brief — Re-authentication needed</h2>
  <p>Your OnTrack session has expired. To continue receiving your daily briefs,
     please re-subscribe using the bookmarklet:</p>
  <p><a href="{app_url}" style="background:#1a5fa8;color:#fff;padding:10px 20px;
     border-radius:5px;text-decoration:none;display:inline-block">Re-subscribe →</a></p>
  <p style="color:#888;font-size:12px">Tip: you don't need to stay logged in to OnTrack —
     just don't click <em>Log Out</em>.</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "OnTrack Brief — Re-authentication needed"
    msg["From"]    = f"OnTrack Brief <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())
        log.info("Re-auth email sent to %s", recipient)
        return True
    except Exception as exc:
        log.error("SMTP failure sending re-auth to %s: %s", recipient, exc)
        return False


def send_brief_to(html: str, recipient: str, today: date, cfg: configparser.ConfigParser) -> bool:
    """Send a brief to a specific recipient using the sender creds in cfg."""
    sender   = cfg["email"]["sender"]
    password = cfg["email"]["app_password"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📚 OnTrack Brief — {today.strftime('%a %b %d')}"
    msg["From"]    = f"OnTrack Brief <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())
        log.info("Brief sent to %s", recipient)
        return True
    except Exception as exc:
        log.error("SMTP failure sending to %s: %s", recipient, exc)
        return False
