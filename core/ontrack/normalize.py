"""Pure OnTrack task/feedback shaping — no HTTP, no auth, no DB.

Shared by the API fetcher (`fetcher.py`, server-pull path) and the `/ingest`
route (extension-capture path) so both normalise captured data identically.
"""

from __future__ import annotations

_GRADE_LABELS = {
    0: "P (Pass)",
    1: "C (Credit)",
    2: "D (Distinction)",
    3: "HD (High Distinction)",
}


def enrich_tasks(tasks: list[dict], task_defs: list[dict]) -> None:
    """Fill each task's display fields (name, deadline, grade label) from its
    task definition. Mutates ``tasks`` in place."""
    td_by_id = {td["id"]: td for td in task_defs}
    for t in tasks:
        td = td_by_id.get(t["task_definition_id"], {})
        t["abbreviation"] = t.get("abbreviation") or td.get("abbreviation", "")
        t["name"] = t.get("name") or td.get("name", "")
        t["target_grade"] = (
            t.get("target_grade") if t.get("target_grade") is not None else td.get("target_grade")
        )
        t["target_grade_label"] = _GRADE_LABELS.get(t.get("target_grade"), "P (Pass)")
        t["due_date"] = t.get("due_date") or td.get("target_date") or td.get("due_date")
        # Rank/window by the target_date the student actually sees in OnTrack, not
        # the hard due_date (often the late-penalty cutoff / end of trimester). Fall
        # back to due_date when a definition has no target.
        t["deadline"] = t.get("deadline") or td.get("target_date") or td.get("due_date")
        t["status_label"] = t.get("status_label") or t.get("status", "").replace("_", " ").title()


def append_missing_tasks(tasks: list[dict], task_defs: list[dict]) -> None:
    """Synthesise not-yet-started task rows for any definition the student hasn't
    engaged with yet. Mutates ``tasks`` in place.

    Includes definitions whose ``start_date`` is still in the future: this is a
    plan-ahead brief, so an upcoming task should surface as soon as it has a
    target date. The deadline window (in the snapshot/brief) is what bounds which
    of these actually display, so synthesising them here never over-shows."""
    submitted_def_ids = {t["task_definition_id"] for t in tasks}
    for td in task_defs:
        if td["id"] in submitted_def_ids:
            continue
        tasks.append(
            {
                "id": None,
                "task_definition_id": td["id"],
                "abbreviation": td["abbreviation"],
                "name": td["name"],
                "status": "not_started",
                "status_label": "Not Started",
                "target_grade": td.get("target_grade"),
                "target_grade_label": _GRADE_LABELS.get(td.get("target_grade"), "P (Pass)"),
                "due_date": td.get("target_date") or td.get("due_date"),
                "deadline": td.get("target_date") or td.get("due_date"),
                "submission_date": None,
                "completion_date": None,
                "extensions": 0,
                "grade": None,
                "is_overdue": False,
            }
        )


def extract_latest_feedback(comments: list, student_id: int | None) -> str | None:
    """Return the most recent tutor text comment (skipping the student's own), or None."""
    if not isinstance(comments, list):
        return None
    for comment in reversed(comments):
        if comment.get("type") != "text":
            continue
        author_id = (comment.get("author") or {}).get("id")
        if author_id and author_id == student_id:
            continue
        text = (comment.get("comment") or "").strip()
        if text:
            return text
    return None
