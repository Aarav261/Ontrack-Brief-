"""HTML rendering for the morning brief email."""

from __future__ import annotations

from datetime import date

from .constants import GRADE_SHORT, GRADE_COLOR, STATUS_LABEL, STATUS_COLOR

_STATUS_BG = {
    "not_started":        "#f0f2f2",
    "working_on_it":      "#e8f4fc",
    "redo_submission":    "#fde8e7",
    "fix_and_resubmit":   "#fde8e7",
    "time_exceeded":      "#fde8e7",
    "need_help":          "#fef0e6",
    "ready_for_feedback": "#f0f2f2",
    "discuss":            "#f3e8fb",
    "demonstrate":        "#f3e8fb",
    "complete":           "#e6f9ee",
    "fail":               "#f2f3f4",
}

_ACCENT_BG = {
    "#c0392b": "#fdf2f2",
    "#2471a3": "#eef6fc",
    "#7d3c98": "#f5f0fb",
    "#7f8c8d": "#f4f6f6",
    "#1e8449": "#f0faf4",
}

_ACCENT_BORDER = {
    "#c0392b": "#f1a9a3",
    "#2471a3": "#a8cfe8",
    "#7d3c98": "#d5b8ef",
    "#7f8c8d": "#bfc9ca",
    "#1e8449": "#a2d9b1",
}


_ALREADY_SUBMITTED = frozenset({"ready_for_feedback", "discuss", "demonstrate", "complete", "fail"})


def _deadline_html(task: dict, today: date) -> str:
    due = task.get("due_date")
    if not due:
        return (
            '<td bgcolor="#ffffff" style="padding:9px 14px;font-size:12px;'
            'color:#aaaaaa;font-weight:700;white-space:nowrap">—</td>'
        )

    days   = (date.fromisoformat(due) - today).days
    status = task.get("status", "")

    if days < 0 and status in _ALREADY_SUBMITTED:
        raw = task.get("submission_date") or task.get("completion_date")
        if raw:
            try:
                sub  = date.fromisoformat(raw[:10])
                text = f"submitted {sub.strftime('%b')} {sub.day}"
            except ValueError:
                text = "submitted"
        else:
            text = "submitted"
        color = "#7f8c8d"
    elif days < 0:
        color, text = "#c0392b", f"{abs(days)}d overdue"
    elif days == 0:
        color, text = "#c0392b", "due today"
    elif days <= 3:
        color, text = "#cb4335", f"{days}d left"
    elif days <= 7:
        color, text = "#d68910", f"{days}d left"
    else:
        color, text = "#444444", f"{days}d left"

    return (
        f'<td bgcolor="#ffffff" style="padding:9px 14px;font-size:12px;color:{color};'
        f'font-weight:700;white-space:nowrap">{text}</td>'
    )


def _grade_badge(task: dict) -> str:
    label = task.get("target_grade_label", "P (Pass)")
    short = GRADE_SHORT.get(label, "?")
    color = GRADE_COLOR.get(label, "#555")
    return (
        f'<span style="background:{color};color:#ffffff;padding:2px 7px;'
        f'border-radius:3px;font-size:11px;font-weight:700;'
        f'font-family:monospace;letter-spacing:0.5px">{short}</span>'
    )


def _status_badge(status: str) -> str:
    label  = STATUS_LABEL.get(status, status)
    color  = STATUS_COLOR.get(status, "#888888")
    bg     = _STATUS_BG.get(status, "#f0f0f0")
    return (
        f'<span style="color:{color};background:{bg};'
        f'border:1px solid {color};'
        f'padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;'
        f'white-space:nowrap">{label}</span>'
    )


def _task_row(task: dict, unit: str, today: date, striped: bool, feedback: str | None = None) -> str:
    bg = "#f8f9fa" if striped else "#ffffff"
    td = f'bgcolor="{bg}" style="background:{bg}'
    row = (
        f'<tr>'
        f'<td {td};padding:9px 14px;font-family:monospace;font-size:12px;'
        f'color:#666666;white-space:nowrap">{unit}</td>'
        f'<td {td};padding:9px 14px;font-size:13px;font-weight:700;'
        f'white-space:nowrap;color:#111111">{task["abbreviation"]}</td>'
        f'<td {td};padding:9px 14px;font-size:13px;color:#222222">'
        + (f'<a href="{task["_url"]}" style="color:#1a5fa8;text-decoration:none" target="_blank">{task["name"]}</a>'
           if task.get("_url") else task["name"])
        + '</td>'
        f'<td {td};padding:9px 14px">{_grade_badge(task)}</td>'
        f'<td {td};padding:9px 14px">{_status_badge(task["status"])}</td>'
        f'{_deadline_html(task, today)}'
        f'</tr>'
    )
    if feedback:
        safe = feedback.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        row += (
            f'<tr>'
            f'<td bgcolor="{bg}" style="background:{bg};padding:0 14px 10px 14px"></td>'
            f'<td bgcolor="{bg}" colspan="5" style="background:{bg};padding:0 14px 10px 14px">'
            f'<table cellpadding="0" cellspacing="0" width="100%"><tr>'
            f'<td bgcolor="#fffbee" style="background:#fffbee;border-left:3px solid #e6960a;'
            f'padding:8px 12px;border-radius:0 4px 4px 0;'
            f'font-size:12px;color:#444444;line-height:1.5">'
            f'<span style="font-weight:700;color:#9a6500;font-size:11px;'
            f'text-transform:uppercase;letter-spacing:0.5px">Tutor feedback &nbsp;&middot;&nbsp; </span>'
            f'{safe}'
            f'</td></tr></table>'
            f'</td></tr>'
        )
    return row


def _section_html(title: str, emoji: str, accent: str, entries: list, today: date, cap: int = 999) -> str:
    if not entries:
        return ""

    rows     = "".join(_task_row(t, u, today, i % 2 == 1, f) for i, (t, u, f) in enumerate(entries[:cap]))
    thead_bg = _ACCENT_BG.get(accent, "#f4f6f6")
    border   = _ACCENT_BORDER.get(accent, "#cccccc")

    overflow = ""
    if len(entries) > cap:
        overflow = (
            f'<tr><td colspan="6" bgcolor="#ffffff" '
            f'style="padding:8px 14px;font-size:12px;color:#aaaaaa;'
            f'text-align:center;font-style:italic">'
            f'+ {len(entries) - cap} more tasks not shown</td></tr>'
        )

    th = (f'style="padding:8px 14px;text-align:left;font-size:10px;text-transform:uppercase;'
          f'color:#666666;font-weight:600;letter-spacing:0.8px;'
          f'background:{thead_bg};border-bottom:2px solid {border}"')

    return f"""
<h2 style="margin:28px 0 10px;font-size:15px;font-weight:700;color:{accent};letter-spacing:0.3px">{emoji}&nbsp; {title}</h2>
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#ffffff"
       style="border-collapse:collapse;background:#ffffff">
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


def _stat_cell(value: int, label: str) -> str:
    return (
        f'<td width="25%" style="text-align:center;padding:0 8px">'
        f'<div style="font-size:30px;font-weight:800;color:#ffffff;line-height:1">{value}</div>'
        f'<div style="font-size:10px;color:#a0b4cc;text-transform:uppercase;'
        f'letter-spacing:1.2px;margin-top:4px">{label}</div>'
        f'</td>'
    )


def render_html(brief: dict, projects: list[dict], today: date, max_todo: int = 10) -> str:
    units = " &middot; ".join(p["unit"]["code"] for p in projects)

    def _cap(items: list) -> list:
        return items[:max_todo]

    stats = "".join([
        _stat_cell(len(brief["urgent"]),    "Urgent"),
        _stat_cell(len(brief["todo"]),      "To Do"),
        _stat_cell(len(brief["waiting"]),   "Discuss"),
        _stat_cell(len(brief["submitted"]), "Submitted"),
    ])

    body = "".join([
        _section_html("Needs Attention",              "🚨", "#c0392b", _cap(brief["urgent"]),    today),
        _section_html("Upcoming Tasks",               "🎯", "#2471a3", _cap(brief["todo"]),      today),
        _section_html("Discuss with Tutor",           "💬", "#7d3c98", _cap(brief["waiting"]),   today),
        _section_html("Submitted – Waiting on Tutor", "📬", "#7f8c8d", _cap(brief["submitted"]), today),
        _section_html("Recently Completed",           "✅", "#1e8449", _cap(brief["done"]),      today),
    ])

    if not body.strip():
        body = (
            '<p style="text-align:center;color:#888888;padding:48px 0;font-size:16px">'
            '&#x1F389; Nothing outstanding &#x2014; you\'re all caught up!</p>'
        )

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
    [data-ogsc] body, [data-ogsb] body {{ background-color:#efefef !important; }}
    body {{ background-color:#efefef; }}
  </style>
</head>
<body bgcolor="#efefef" style="margin:0;padding:0;background:#efefef;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#efefef"
         style="background:#efefef;padding:24px 0">
    <tr><td align="center">
      <table width="720" cellpadding="0" cellspacing="0" style="max-width:720px;width:100%">

        <!-- Header (intentionally dark — stays dark in dark mode, looks fine) -->
        <tr><td style="padding-bottom:8px">
          <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#16213e"
                 style="background:#16213e;border-radius:10px;padding:28px 32px">
            <tr>
              <td>
                <div style="font-size:10px;color:#7a9abf;text-transform:uppercase;
                            letter-spacing:2px;margin-bottom:4px">
                  OnTrack Morning Brief
                </div>
                <div style="font-size:22px;font-weight:800;color:#ffffff;margin-bottom:2px">
                  {today.strftime("%A, %B %d %Y")}
                </div>
                <div style="font-size:12px;color:#7a9abf;margin-bottom:22px">
                  {units}
                </div>
              </td>
            </tr>
            <tr>
              <td style="border-top:1px solid #2d4a6e;padding-top:18px">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>{stats}</tr>
                </table>
              </td>
            </tr>
          </table>
        </td></tr>

        <!-- Body -->
        <tr><td>
          <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#ffffff"
                 style="background:#ffffff;border-radius:10px;padding:24px 28px">
            <tr><td>
              {body}
            </td></tr>
          </table>
        </td></tr>

        <!-- Footer -->
        <tr><td bgcolor="#efefef" style="background:#efefef;text-align:center;
                       padding:14px 0;font-size:11px;color:#aaaaaa">
          ontrack-morning-brief
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
