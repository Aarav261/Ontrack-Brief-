"""Brief construction — categorise/prioritise OnTrack tasks and render the email.

Public API for the rest of the app; internals live in `builder.py` and `renderer.py`.
"""

from .builder import build_brief_direct, is_hidden, pending_task_entries
from .renderer import pending_due_entries, render_html

__all__ = [
    "build_brief_direct",
    "is_hidden",
    "pending_task_entries",
    "pending_due_entries",
    "render_html",
]
