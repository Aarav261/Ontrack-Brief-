"""A short inspirational quote for the email footer.

Uses ZenQuotes (https://zenquotes.io) — free, no API key, returns
``[{"q": <quote>, "a": <author>}]``. Network is best-effort: any failure or
slow response falls back to a curated static quote so an email never breaks or
blocks on the quote service.
"""

from __future__ import annotations

import logging
import random

import requests

log = logging.getLogger(__name__)

_ZENQUOTES_URL = "https://zenquotes.io/api/random"
_TIMEOUT = 5  # seconds — keep short; the email must not wait on this

# Curated fallback (no emojis). Also used when ZenQuotes rate-limits (free tier
# allows ~5 requests / 30s per IP, so a morning batch will lean on these).
_FALLBACK: list[tuple[str, str]] = [
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("Well done is better than well said.", "Benjamin Franklin"),
    ("Quality is not an act, it is a habit.", "Aristotle"),
    ("The future depends on what you do today.", "Mahatma Gandhi"),
    ("Discipline is the bridge between goals and accomplishment.", "Jim Rohn"),
    ("Little by little, one travels far.", "J.R.R. Tolkien"),
    ("Continuous effort unlocks more than talent ever does.", "Winston Churchill"),
    ("Start where you are. Use what you have. Do what you can.", "Arthur Ashe"),
    ("The expert in anything was once a beginner.", "Helen Hayes"),
]


def get_inspirational_quote() -> tuple[str, str]:
    """Return ``(quote, author)`` — from ZenQuotes, or a fallback on any failure."""
    try:
        r = requests.get(_ZENQUOTES_URL, timeout=_TIMEOUT)
        r.raise_for_status()
        item = r.json()[0]
        text = (item.get("q") or "").strip()
        author = (item.get("a") or "Unknown").strip()
        if text:
            return text, author or "Unknown"
    except Exception as exc:  # network error, rate limit, bad payload — all non-fatal
        log.info("Quote service unavailable, using fallback: %s", exc)
    return random.choice(_FALLBACK)
