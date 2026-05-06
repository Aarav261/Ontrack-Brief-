"""Email delivery for the morning brief."""

from __future__ import annotations

import configparser
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(html: str, cfg: configparser.ConfigParser, today: date) -> None:
    sender    = cfg["email"]["sender"]
    recipient = cfg["email"]["recipient"]
    password  = cfg["email"]["app_password"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📚 OnTrack Brief — {today.strftime('%a %b %d')}"
    msg["From"]    = f"OnTrack Brief <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, recipient, msg.as_string())

    print(f"✓ Brief sent to {recipient}")


def send_brief_to(html: str, recipient: str, today: date, cfg: configparser.ConfigParser) -> None:
    """Send a brief to a specific recipient using the sender creds in cfg."""
    sender   = cfg["email"]["sender"]
    password = cfg["email"]["app_password"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📚 OnTrack Brief — {today.strftime('%a %b %d')}"
    msg["From"]    = f"OnTrack Brief <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, recipient, msg.as_string())

    print(f"✓ Brief sent to {recipient}")
