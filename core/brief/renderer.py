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

    return (
        f'<tr>'
        f'<td style="padding:8px 10px 8px 0;font-size:11px;font-family:monospace;'
        f'color:#777777;white-space:nowrap;border-bottom:1px solid #f0f0f0">{unit_code}</td>'
        f'<td style="padding:8px 10px 8px 0;font-size:11px;font-family:monospace;'
        f'color:#aaaaaa;white-space:nowrap;border-bottom:1px solid #f0f0f0">{abbrev}</td>'
        f'<td style="padding:8px 16px 8px 0;font-size:13px;border-bottom:1px solid #f0f0f0;width:99%">'
        f'{name_cell}</td>'
        f'<td style="padding:8px 0;border-bottom:1px solid #f0f0f0;white-space:nowrap;font-size:12px;color:#555555">'
        f'{_due_label(due, today)}</td>'
        f'</tr>'
    )


def render_html(pending_entries: list[dict], today: date, window_days: int = 14) -> str:
    font = "'Helvetica Neue',Helvetica,Arial,sans-serif"
    title = f"Pending tasks due in the next {window_days} days"

    if not pending_entries:
        body = (
            f'<p style="text-align:left;color:#777777;padding:12px 0 0;font-size:14px;'
            f'line-height:1.5">No pending tasks due in the next {window_days} days.</p>'
        )
    else:
        rows = "".join(_task_row(entry, today) for entry in pending_entries)
        body = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px">
  <thead>
    <tr>
      <th style="padding:6px 10px 6px 0;font-size:10px;text-transform:uppercase;color:#bbbbbb;letter-spacing:1px;text-align:left;border-bottom:2px solid #f0f0f0">Unit</th>
      <th style="padding:6px 10px 6px 0;font-size:10px;text-transform:uppercase;color:#bbbbbb;letter-spacing:1px;text-align:left;border-bottom:2px solid #f0f0f0">Task</th>
      <th style="padding:6px 16px 6px 0;font-size:10px;text-transform:uppercase;color:#bbbbbb;letter-spacing:1px;text-align:left;border-bottom:2px solid #f0f0f0">Name</th>
      <th style="padding:6px 0;font-size:10px;text-transform:uppercase;color:#bbbbbb;letter-spacing:1px;text-align:left;border-bottom:2px solid #f0f0f0">Due</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>"""

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>OnTrack Brief</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ background-color:#f5f4f0 !important; }}
  </style>
</head>
<body bgcolor="#f5f4f0" style="margin:0;padding:0;background:#f5f4f0;font-family:{font}">
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f5f4f0"
         style="background:#f5f4f0;padding:24px 0 32px">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0"
             style="max-width:640px;width:100%">
        <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:20px 24px;border-radius:8px">
          <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#999999;font-weight:600;margin-bottom:6px;font-family:{font}">
            OnTrack Brief
          </div>
          <div style="font-size:20px;font-weight:700;color:#111111;font-family:{font};margin-bottom:8px">
            {title}
          </div>
          {body}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
