"""Build the prioritised brief from fetched project/task data."""

from __future__ import annotations

from datetime import date

from core.constants import GRADE_WEIGHT, URGENT, TODO, WAITING, SUBMITTED, DONE
from core.ontrack import (
    fetch_tasks,
    fetch_last_feedback,
    fetch_tasks_direct,
    fetch_last_feedback_direct,
)
from core.ontrack.fetcher import _api_auth


def _safe_date(task: dict) -> date:
    """Parse due_date safely, returning date.max when missing or malformed."""
    due = task.get("due_date", "")
    if not due:
        return date.max
    try:
        return date.fromisoformat(due)
    except ValueError:
        return date.max


def _score(task: dict, today: date) -> tuple:
    """Sort key applied to every section.

    Priority order:
      1. Red band first  (overdue or ≤ 3 days left)
      2. Grade descending within band  (HD > D > C > P)
      3. Days left ascending  (sooner deadline first)
      4. Urgency tier as final tiebreaker
    """
    deadline = _safe_date(task)
    days_left = (deadline - today).days if deadline is not date.max else 999
    grade_weight = GRADE_WEIGHT.get(task.get("target_grade_label", "P (Pass)"), 0)
    status = task["status"]

    red_band = 0 if days_left <= 3 else 1  # 0 = red → floats to top

    if status == "time_exceeded":
        tier = 0
    elif status in {"redo_submission", "fix_and_resubmit"}:
        tier = 1
    elif status == "need_help":
        tier = 2
    else:
        tier = 3

    return (red_band, -grade_weight, days_left, tier)


def _build_brief(
    projects: list[dict],
    *,
    base_url: str,
    recently_completed_days: int,
    task_fetcher,
    feedback_fetcher,
) -> dict:
    today = date.today()
    urgent, todo, waiting, submitted, done = [], [], [], [], []

    for project in projects:
        project_id = project["id"]
        unit_code = project["unit"]["code"]

        for task in task_fetcher(project_id):
            task["_url"] = (
                f"{base_url}/projects/{project_id}/dashboard/{task['abbreviation']}"
            )
            status = task["status"]

            if status in DONE:
                comp = task.get("completion_date")
                if (
                    comp
                    and (today - date.fromisoformat(comp)).days
                    <= recently_completed_days
                ):
                    done.append((task, unit_code, None))
            elif status in URGENT:
                feedback = feedback_fetcher(project_id, task["task_definition_id"])
                urgent.append((task, unit_code, feedback))
            elif status in TODO:
                todo.append((task, unit_code, None))
            elif status in WAITING:
                feedback = feedback_fetcher(project_id, task["task_definition_id"])
                waiting.append((task, unit_code, feedback))
            elif status in SUBMITTED:
                submitted.append((task, unit_code, None))

    sort_key = lambda e: _score(e[0], today)
    urgent.sort(key=sort_key)
    todo.sort(key=sort_key)
    waiting.sort(key=sort_key)
    submitted.sort(key=sort_key)
    done.sort(key=lambda e: e[0].get("completion_date", ""), reverse=True)

    return {
        "urgent": urgent,
        "todo": todo,
        "waiting": waiting,
        "submitted": submitted,
        "done": done,
    }


def build_brief(projects: list[dict], recently_completed_days: int = 7) -> dict:
    base_url, _, _ = _api_auth()

    def task_fetcher(project_id: int) -> list[dict]:
        return fetch_tasks(project_id)

    def feedback_fetcher(project_id: int, task_def_id: int) -> str | None:
        return fetch_last_feedback(project_id, task_def_id)

    return _build_brief(
        projects,
        base_url=base_url,
        recently_completed_days=recently_completed_days,
        task_fetcher=task_fetcher,
        feedback_fetcher=feedback_fetcher,
    )


def build_brief_direct(
    base_url: str,
    auth_token: str,
    username: str,
    projects: list[dict],
    recently_completed_days: int = 7,
    session=None,
) -> dict:
    student_id: int | None = None
    if projects:
        user = projects[0].get("user") or {}
        student_id = user.get("id")

    def task_fetcher(project_id: int) -> list[dict]:
        return fetch_tasks_direct(
            base_url, auth_token, username, project_id, session=session
        )

    def feedback_fetcher(project_id: int, task_def_id: int) -> str | None:
        return fetch_last_feedback_direct(
            base_url,
            auth_token,
            username,
            project_id,
            task_def_id,
            student_id,
            session=session,
        )

    return _build_brief(
        projects,
        base_url=base_url,
        recently_completed_days=recently_completed_days,
        task_fetcher=task_fetcher,
        feedback_fetcher=feedback_fetcher,
    )
