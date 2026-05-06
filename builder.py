"""Build the prioritised brief from fetched project/task data."""

from __future__ import annotations

from datetime import date

from constants import GRADE_WEIGHT, URGENT, TODO, WAITING, SUBMITTED, DONE
from fetcher import (
    fetch_tasks, fetch_last_feedback, _api_auth,
    fetch_tasks_direct, fetch_last_feedback_direct,
)


def _score(task: dict, today: date) -> tuple:
    """Lower tuple = higher priority. Urgency tier first, then deadline adjusted for grade."""
    deadline    = date.fromisoformat(task["due_date"])
    days_left   = (deadline - today).days
    grade_bonus = GRADE_WEIGHT.get(task.get("target_grade_label", "P (Pass)"), 0) * 7
    status      = task["status"]

    if status == "time_exceeded":
        return (0, days_left - grade_bonus)
    if status in {"redo_submission", "fix_and_resubmit"}:
        return (1, days_left - grade_bonus)
    if status == "need_help":
        return (2, days_left - grade_bonus)
    return (3, days_left - grade_bonus)


def build_brief(projects: list[dict], recently_completed_days: int = 7) -> dict:
    today = date.today()
    urgent, todo, waiting, submitted, done = [], [], [], [], []

    base_url, _, _ = _api_auth()

    for project in projects:
        project_id = project["id"]
        unit_code  = project["unit"]["code"]

        for task in fetch_tasks(project_id):
            task["_url"] = f"{base_url}/projects/{project_id}/dashboard/{task['abbreviation']}"
            status = task["status"]

            if status in DONE:
                comp = task.get("completion_date")
                if comp and (today - date.fromisoformat(comp)).days <= recently_completed_days:
                    done.append((task, unit_code, None))
            elif status in URGENT:
                feedback = fetch_last_feedback(project_id, task["task_definition_id"])
                urgent.append((task, unit_code, feedback))
            elif status in TODO:
                todo.append((task, unit_code, None))
            elif status in WAITING:
                feedback = fetch_last_feedback(project_id, task["task_definition_id"])
                waiting.append((task, unit_code, feedback))
            elif status in SUBMITTED:
                submitted.append((task, unit_code, None))

    sort_key = lambda e: _score(e[0], today)
    urgent.sort(key=sort_key)
    todo.sort(key=sort_key)
    waiting.sort(key=lambda e: date.fromisoformat(e[0]["due_date"]))
    submitted.sort(key=lambda e: date.fromisoformat(e[0]["due_date"]))
    done.sort(key=lambda e: e[0].get("completion_date", ""), reverse=True)

    return {"urgent": urgent, "todo": todo, "waiting": waiting, "submitted": submitted, "done": done}


def build_brief_direct(
    base_url: str,
    auth_token: str,
    username: str,
    projects: list[dict],
    recently_completed_days: int = 7,
) -> dict:
    today = date.today()
    urgent, todo, waiting, submitted, done = [], [], [], [], []

    student_id: int | None = None
    if projects:
        user = projects[0].get("user") or {}
        student_id = user.get("id")

    for project in projects:
        project_id = project["id"]
        unit_code  = project["unit"]["code"]

        for task in fetch_tasks_direct(base_url, auth_token, username, project_id):
            if not task.get("due_date"):
                continue
            task["_url"] = f"{base_url}/projects/{project_id}/dashboard/{task['abbreviation']}"
            status = task["status"]

            if status in DONE:
                comp = task.get("completion_date")
                if comp and (today - date.fromisoformat(comp)).days <= recently_completed_days:
                    done.append((task, unit_code, None))
            elif status in URGENT:
                feedback = fetch_last_feedback_direct(
                    base_url, auth_token, username,
                    project_id, task["task_definition_id"], student_id,
                )
                urgent.append((task, unit_code, feedback))
            elif status in TODO:
                todo.append((task, unit_code, None))
            elif status in WAITING:
                feedback = fetch_last_feedback_direct(
                    base_url, auth_token, username,
                    project_id, task["task_definition_id"], student_id,
                )
                waiting.append((task, unit_code, feedback))
            elif status in SUBMITTED:
                submitted.append((task, unit_code, None))

    sort_key = lambda e: _score(e[0], today)
    urgent.sort(key=sort_key)
    todo.sort(key=sort_key)
    waiting.sort(key=lambda e: date.fromisoformat(e[0]["due_date"]))
    submitted.sort(key=lambda e: date.fromisoformat(e[0]["due_date"]))
    done.sort(key=lambda e: e[0].get("completion_date", ""), reverse=True)

    return {"urgent": urgent, "todo": todo, "waiting": waiting, "submitted": submitted, "done": done}
