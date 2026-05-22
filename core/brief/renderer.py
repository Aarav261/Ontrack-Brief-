"""HTML rendering for the morning brief email."""

from __future__ import annotations

from datetime import date


def pending_due_entries(brief: dict, today: date, days_ahead: int) -> list[dict]:
    entries: list[dict] = []
    for key in ("urgent", "todo", "waiting"):
        for task, unit, _ in brief.get(key, []):
            due_raw = task.get("due_date")
            if not due_raw:
                continue
            try:
                due = date.fromisoformat(due_raw)
            except ValueError:
                continue
            days = (due - today).days
            if 0 <= days <= days_ahead:
                entries.append({"task": task, "unit": unit, "due": due})
    entries.sort(key=lambda entry: (entry["due"], entry["unit"], entry["task"].get("name", "")))
    return entries


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _due_label(due: date, today: date) -> str:
    days = (due - today).days
    if days == 0:
        suffix = "Today"
    elif days == 1:
        suffix = "Tomorrow"
    else:
        suffix = f"{days}d"
    return f"{due.strftime('%b')} {due.day} ({suffix})"


def _due_color(due: date, today: date) -> str:
    days = (due - today).days
    if days <= 0:
        return "#ef4444"
    if days <= 3:
        return "#ff6b6b"
    if days <= 7:
        return "#fbbf24"
    return "#555555"


def _task_row(entry: dict, today: date) -> str:
    task = entry["task"]
    unit = entry["unit"]
    due = entry["due"]

    name = _escape(task.get("name", ""))
    unit_code = _escape(unit)
    abbrev = _escape(task.get("abbreviation", ""))

    if task.get("_url"):
        name_cell = f'<a href="{task["_url"]}" style="color:#111111;text-decoration:none;font-weight:500" target="_blank">{name}</a>'
    else:
        name_cell = f'<span style="color:#111111;font-weight:500">{name}</span>'

    due_color = _due_color(due, today)
    return (
        f'<tr>'
        f'<td style="padding:10px 12px 10px 0;font-size:11px;font-family:monospace;'
        f'color:#666666;white-space:nowrap;border-bottom:1px solid #e8e8e8">{unit_code}</td>'
        f'<td style="padding:10px 12px 10px 0;font-size:11px;font-family:monospace;'
        f'color:#9a9a9a;white-space:nowrap;border-bottom:1px solid #e8e8e8">{abbrev}</td>'
        f'<td style="padding:10px 18px 10px 0;font-size:13px;border-bottom:1px solid #e8e8e8;width:99%">'
        f'{name_cell}</td>'
        f'<td style="padding:10px 0;border-bottom:1px solid #e8e8e8;white-space:nowrap;'
        f'font-size:12px;color:{due_color};font-weight:700">'
        f'{_due_label(due, today)}</td>'
        f'</tr>'
    )


def render_html(pending_entries: list[dict], today: date, window_days: int = 14) -> str:
    font = "'Lora', Georgia, 'Times New Roman', serif"
    title = f"Pending tasks due in the next {window_days} days"

    if not pending_entries:
        body = (
            f'<p style="text-align:left;color:#777777;padding:12px 0 0;font-size:14px;'
            f'line-height:1.6">No pending tasks due in the next {window_days} days.</p>'
        )
    else:
        rows = "".join(_task_row(entry, today) for entry in pending_entries)
        body = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px">
  <thead>
    <tr>
      <th style="padding:8px 12px 8px 0;font-size:10px;text-transform:uppercase;color:#888888;letter-spacing:.9px;text-align:left;border-bottom:2px solid #e8e8e8">Unit</th>
      <th style="padding:8px 12px 8px 0;font-size:10px;text-transform:uppercase;color:#888888;letter-spacing:.9px;text-align:left;border-bottom:2px solid #e8e8e8">Task</th>
      <th style="padding:8px 18px 8px 0;font-size:10px;text-transform:uppercase;color:#888888;letter-spacing:.9px;text-align:left;border-bottom:2px solid #e8e8e8">Name</th>
      <th style="padding:8px 0;font-size:10px;text-transform:uppercase;color:#888888;letter-spacing:.9px;text-align:left;border-bottom:2px solid #e8e8e8">Due</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>"""

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>OnTrack Brief</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ background-color:#ffffff !important; }}
    @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');
    @media (prefers-color-scheme: dark) {{
      body {{
        background-color:#0a0a0a !important;
        color:#f5f5f5 !important;
      }}
      a {{ color:#8aa0ff !important; }}
    }}
  </style>
</head>
<body bgcolor="#ffffff" style="margin:0;padding:0;background:#ffffff;font-family:{font}">
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#ffffff"
         style="background:#ffffff;padding:28px 0 36px">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0"
             style="max-width:640px;width:100%">
        <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:24px 28px;border-radius:12px">
          <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#999999;font-weight:700;margin-bottom:8px;font-family:{font}">
            OnTrack Brief
          </div>
          <div style="font-size:22px;font-weight:800;color:#4361EE;font-family:{font};margin-bottom:12px;letter-spacing:-0.3px">
            {title}
          </div>
          {body}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
