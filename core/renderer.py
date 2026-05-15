"""HTML rendering for the morning brief email."""

from __future__ import annotations

from datetime import date

from .constants import GRADE_SHORT, GRADE_COLOR, STATUS_LABEL, STATUS_COLOR

_ALREADY_SUBMITTED = frozenset({"ready_for_feedback", "discuss", "demonstrate", "complete", "fail"})

_SECTION_COLOR = {
    "urgent":    "#c0392b",
    "todo":      "#1a5fa8",
    "waiting":   "#7d3c98",
    "submitted": "#7f8c8d",
    "done":      "#27ae60",
}

_SECTION_LABEL = {
    "urgent":    "NEEDS ATTENTION",
    "todo":      "UPCOMING TASKS",
    "waiting":   "DISCUSS WITH TUTOR",
    "submitted": "SUBMITTED",
    "done":      "RECENTLY COMPLETED",
}

_DUE_URGENT_BG   = "#fff5f5"
_DUE_URGENT_TEXT = "#c0392b"
_DUE_WARN_BG     = "#fffbf0"
_DUE_WARN_TEXT   = "#b7770d"
_DUE_OK_TEXT     = "#555555"


def _deadline_html(task: dict, today: date) -> str:
    due = task.get("due_date")
    if not due:
        return '<td style="padding:10px 12px 10px 0;font-size:12px;color:#cccccc;white-space:nowrap;border-bottom:1px solid #f0f0f0">—</td>'

    days   = (date.fromisoformat(due) - today).days
    status = task.get("status", "")

    if days < 0 and status in _ALREADY_SUBMITTED:
        raw = task.get("submission_date") or task.get("completion_date")
        if raw:
            try:
                sub  = date.fromisoformat(raw[:10])
                text = f"Submitted {sub.strftime('%b')} {sub.day}"
            except ValueError:
                text = "Submitted"
        else:
            text = "Submitted"
        return (
            f'<td style="padding:10px 12px 10px 0;font-size:12px;color:#aaaaaa;'
            f'white-space:nowrap;border-bottom:1px solid #f0f0f0">{text}</td>'
        )
    elif days < 0:
        label = f"{abs(days)}d overdue"
        return (
            f'<td style="padding:10px 12px 10px 0;white-space:nowrap;border-bottom:1px solid #f0f0f0">'
            f'<span style="background:{_DUE_URGENT_BG};color:{_DUE_URGENT_TEXT};'
            f'font-size:11px;font-weight:700;padding:2px 7px;border-radius:2px">{label}</span></td>'
        )
    elif days == 0:
        return (
            f'<td style="padding:10px 12px 10px 0;white-space:nowrap;border-bottom:1px solid #f0f0f0">'
            f'<span style="background:{_DUE_URGENT_BG};color:{_DUE_URGENT_TEXT};'
            f'font-size:11px;font-weight:700;padding:2px 7px;border-radius:2px">Due today</span></td>'
        )
    elif days <= 3:
        return (
            f'<td style="padding:10px 12px 10px 0;white-space:nowrap;border-bottom:1px solid #f0f0f0">'
            f'<span style="background:{_DUE_WARN_BG};color:{_DUE_WARN_TEXT};'
            f'font-size:11px;font-weight:700;padding:2px 7px;border-radius:2px">{days}d left</span></td>'
        )
    elif days <= 7:
        return (
            f'<td style="padding:10px 12px 10px 0;font-size:12px;color:{_DUE_WARN_TEXT};'
            f'font-weight:600;white-space:nowrap;border-bottom:1px solid #f0f0f0">{days}d left</td>'
        )
    else:
        return (
            f'<td style="padding:10px 12px 10px 0;font-size:12px;color:{_DUE_OK_TEXT};'
            f'white-space:nowrap;border-bottom:1px solid #f0f0f0">{days}d left</td>'
        )


def _grade_badge(task: dict) -> str:
    label = task.get("target_grade_label", "P (Pass)")
    short = GRADE_SHORT.get(label, "?")
    color = GRADE_COLOR.get(label, "#555")
    return (
        f'<span style="background:{color};color:#ffffff;padding:2px 6px;'
        f'border-radius:2px;font-size:10px;font-weight:700;'
        f'letter-spacing:0.5px">{short}</span>'
    )


def _status_chip(status: str) -> str:
    label = STATUS_LABEL.get(status, status)
    color = STATUS_COLOR.get(status, "#888888")
    return f'<span style="color:{color};font-size:12px;font-weight:600">{label}</span>'


def _task_row(task: dict, unit: str, today: date, _striped: bool, feedback: str | None = None) -> str:
    name_cell = (
        f'<a href="{task["_url"]}" style="color:#111111;text-decoration:none;font-weight:500" target="_blank">{task["name"]}</a>'
        if task.get("_url") else
        f'<span style="color:#111111;font-weight:500">{task["name"]}</span>'
    )

    row = (
        f'<tr>'
        f'<td style="padding:10px 10px 10px 0;font-size:11px;font-family:monospace;'
        f'color:#999999;white-space:nowrap;border-bottom:1px solid #f0f0f0;letter-spacing:0.3px">{unit}</td>'
        f'<td style="padding:10px 10px 10px 0;font-size:11px;font-family:monospace;'
        f'color:#aaaaaa;white-space:nowrap;border-bottom:1px solid #f0f0f0">{task["abbreviation"]}</td>'
        f'<td style="padding:10px 16px 10px 0;font-size:13px;border-bottom:1px solid #f0f0f0;width:99%">'
        f'{name_cell}</td>'
        f'<td style="padding:10px 16px 10px 0;border-bottom:1px solid #f0f0f0;white-space:nowrap">{_grade_badge(task)}</td>'
        f'<td style="padding:10px 16px 10px 0;border-bottom:1px solid #f0f0f0;white-space:nowrap">{_status_chip(task["status"])}</td>'
        f'{_deadline_html(task, today)}'
        f'</tr>'
    )

    if feedback:
        safe = feedback.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        row += (
            f'<tr>'
            f'<td style="padding:0;border-bottom:1px solid #f0f0f0"></td>'
            f'<td colspan="5" style="padding:0 0 12px 0;border-bottom:1px solid #f0f0f0">'
            f'<div style="border-left:2px solid #e6960a;padding:6px 10px;'
            f'background:#fffdf5;font-size:12px;color:#555555;line-height:1.5">'
            f'<span style="font-size:10px;font-weight:700;color:#9a6500;text-transform:uppercase;'
            f'letter-spacing:0.8px">Tutor &middot; </span>{safe}'
            f'</div>'
            f'</td></tr>'
        )
    return row


def _section_html(key: str, entries: list, today: date, cap: int = 999) -> str:
    if not entries:
        return ""

    accent = _SECTION_COLOR[key]
    title  = _SECTION_LABEL[key]
    rows   = "".join(_task_row(t, u, today, i % 2 == 1, f) for i, (t, u, f) in enumerate(entries[:cap]))

    overflow = ""
    if len(entries) > cap:
        overflow = (
            f'<tr><td colspan="6" style="padding:8px 0;font-size:11px;color:#bbbbbb;'
            f'text-align:center;letter-spacing:0.5px">+ {len(entries) - cap} more not shown</td></tr>'
        )

    th = (
        'style="padding:6px 10px 6px 0;font-size:10px;text-transform:uppercase;'
        'color:#bbbbbb;font-weight:600;letter-spacing:1px;border-bottom:2px solid #f0f0f0;'
        'white-space:nowrap;text-align:left"'
    )

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:32px">
  <tr>
    <td colspan="6" style="padding-bottom:10px;border-bottom:1px solid #111111">
      <span style="font-size:10px;font-weight:700;letter-spacing:2px;
                   text-transform:uppercase;color:{accent}">{title}</span>
    </td>
  </tr>
</table>
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:2px">
  <thead>
    <tr>
      <th {th}>Unit</th>
      <th {th}>Task</th>
      <th {th}>Name</th>
      <th {th}>Grade</th>
      <th {th}>Status</th>
      <th {th}>Due</th>
    </tr>
  </thead>
  <tbody>{rows}{overflow}</tbody>
</table>"""


def _stat_cell(value: int, label: str, accent: str, last: bool = False) -> str:
    border = "" if last else "border-right:1px solid #f0f0f0;"
    return (
        f'<td width="25%" style="text-align:center;padding:20px 8px;{border}">'
        f'<div style="font-size:36px;font-weight:800;color:{accent};line-height:1;'
        f'font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif">{value}</div>'
        f'<div style="font-size:9px;color:#aaaaaa;text-transform:uppercase;'
        f'letter-spacing:1.5px;margin-top:5px;font-weight:600">{label}</div>'
        f'</td>'
    )


def render_html(brief: dict, projects: list[dict], today: date, max_todo: int = 10) -> str:
    units = " &middot; ".join(p["unit"]["code"] for p in projects)

    def _cap(items: list) -> list:
        return items[:max_todo]

    urgent_n    = len(brief["urgent"])
    todo_n      = len(brief["todo"])
    waiting_n   = len(brief["waiting"])
    submitted_n = len(brief["submitted"])

    stats = "".join([
        _stat_cell(urgent_n,    "Urgent",    "#c0392b" if urgent_n    else "#cccccc"),
        _stat_cell(todo_n,      "To Do",     "#1a5fa8" if todo_n      else "#cccccc"),
        _stat_cell(waiting_n,   "Discuss",   "#7d3c98" if waiting_n   else "#cccccc"),
        _stat_cell(submitted_n, "Submitted", "#27ae60" if submitted_n else "#cccccc", last=True),
    ])

    body = "".join([
        _section_html("urgent",    _cap(brief["urgent"]),    today),
        _section_html("todo",      _cap(brief["todo"]),      today),
        _section_html("waiting",   _cap(brief["waiting"]),   today),
        _section_html("submitted", _cap(brief["submitted"]), today),
        _section_html("done",      _cap(brief["done"]),      today),
    ])

    if not body.strip():
        body = (
            '<p style="text-align:center;color:#aaaaaa;padding:40px 0 20px;font-size:15px;'
            'letter-spacing:0.3px">Nothing outstanding &mdash; you\'re all caught up.</p>'
        )

    day_label   = today.strftime("%A").upper()
    date_short  = f"{today.strftime('%B')} {today.day}"
    year_label  = today.strftime("%Y")

    font = "'Helvetica Neue',Helvetica,Arial,sans-serif"

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>OnTrack Brief &middot; {today.strftime("%b %d")}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ background-color:#f5f4f0 !important; }}
  </style>
</head>
<body bgcolor="#f5f4f0" style="margin:0;padding:0;background:#f5f4f0;font-family:{font}">
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f5f4f0"
         style="background:#f5f4f0;padding:32px 0 48px">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0"
             style="max-width:640px;width:100%">

        <!-- Eyebrow label -->
        <tr><td style="padding-bottom:16px;text-align:left">
          <span style="font-size:10px;letter-spacing:2.5px;text-transform:uppercase;
                       color:#999999;font-weight:600;font-family:{font}">
            OnTrack Brief
          </span>
        </td></tr>

        <!-- Date header -->
        <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:28px 32px 0;
                border-radius:8px 8px 0 0">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                            color:#bbbbbb;font-weight:600;margin-bottom:6px;font-family:{font}">
                  {day_label}
                </div>
                <div style="font-size:38px;font-weight:800;color:#111111;line-height:1;
                            letter-spacing:-0.5px;font-family:{font}">
                  {date_short}
                  <span style="font-size:20px;font-weight:400;color:#bbbbbb;
                               letter-spacing:0;margin-left:4px">{year_label}</span>
                </div>
                <div style="font-size:11px;color:#bbbbbb;margin-top:8px;
                            letter-spacing:0.8px;font-family:{font}">
                  {units}
                </div>
              </td>
            </tr>
          </table>
        </td></tr>

        <!-- Stats bar -->
        <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:0 32px;
                border-bottom:1px solid #f0f0f0">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-top:1px solid #f0f0f0;margin-top:20px">
            <tr>
              {stats}
            </tr>
          </table>
        </td></tr>

        <!-- Body content -->
        <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:8px 32px 36px;
                border-radius:0 0 8px 8px">
          {body}
        </td></tr>

        <!-- Footer -->
        <tr><td style="text-align:center;padding:24px 0 0">
          <span style="font-size:10px;color:#aaaaaa;letter-spacing:0.5px;font-family:{font}">
            OnTrack Brief &nbsp;&middot;&nbsp;
            <a href="#" style="color:#aaaaaa;text-decoration:underline">Unsubscribe</a>
          </span>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
