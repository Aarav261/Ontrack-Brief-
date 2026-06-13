"""Shared HTML shell for all OnTrack Brief emails.

Mirrors the extension's design language: Lora serif, #4361ee accent, near-black
ink on white cards over a light surface, generous spacing. Every email is wrapped
with the same header wordmark and an inspirational-quote footer.
"""

from __future__ import annotations

from core.quotes import get_inspirational_quote

_FONT = "'Lora', Georgia, 'Times New Roman', serif"
_ACCENT = "#4361ee"
_INK = "#0a0a0a"


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _quote_footer() -> str:
    text, author = get_inspirational_quote()
    text = _escape(text)
    author = _escape(author)
    return f"""
<td style="padding:22px 32px;border-top:1px solid #ececec;background:#fafafa;border-radius:0 0 14px 14px">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="padding-left:14px;border-left:3px solid {_ACCENT}">
        <div style="font-family:{_FONT};font-style:italic;font-size:15px;line-height:1.55;color:#3a3a3a">
          {text}
        </div>
        <div style="font-family:{_FONT};font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#9a9a9a;margin-top:8px;font-weight:600">
          {author}
        </div>
      </td>
    </tr>
  </table>
</td>"""


def render_email(
    heading: str,
    inner_html: str,
    *,
    eyebrow: str = "OnTrack Brief",
    with_quote: bool = True,
) -> str:
    """Wrap ``inner_html`` in the shared shell with a header and a quote footer.

    ``heading`` is the section title (accent-coloured); ``eyebrow`` is the small
    uppercase wordmark above it. ``inner_html`` is trusted, pre-escaped content.
    Set ``with_quote=False`` for transactional/admin mail where the inspirational
    quote footer would be out of place (e.g. issue reports).
    """
    quote_row = f"<tr>{_quote_footer()}</tr>" if with_quote else ""
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>{_escape(eyebrow)}</title>
  <style>
    :root {{ color-scheme: light dark; }}
    @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');
    body {{ background-color:#e8e8e8 !important; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background-color:#0a0a0a !important; }}
      a {{ color:#8aa0ff !important; }}
    }}
  </style>
</head>
<body bgcolor="#e8e8e8" style="margin:0;padding:0;background:#e8e8e8;font-family:{_FONT}">
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#e8e8e8"
         style="background:#e8e8e8;padding:32px 16px 40px">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%">
        <tr><td bgcolor="#ffffff"
                style="background:#ffffff;border:1px solid #e3e3e3;border-radius:14px">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="padding:24px 32px 18px;border-bottom:1px solid #ececec">
              <div style="font-size:11px;letter-spacing:2.4px;text-transform:uppercase;color:{_ACCENT};font-weight:700;font-family:{_FONT}">
                {_escape(eyebrow)}
              </div>
              <div style="font-size:24px;font-weight:800;color:{_INK};font-family:{_FONT};margin-top:6px;letter-spacing:-0.4px;line-height:1.25">
                {heading}
              </div>
            </td></tr>
            <tr><td style="padding:22px 32px 26px">
              {inner_html}
            </td></tr>
            {quote_row}
          </table>
        </td></tr>
        <tr><td align="center" style="padding:18px 0 0">
          <div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#b0b0b0;font-family:{_FONT};font-weight:600">
            OnTrack Brief
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
