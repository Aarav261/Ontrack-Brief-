"""Brief construction — categorise/prioritise OnTrack tasks and render the email.

Public API for the rest of the app; internals live in `builder.py` and `renderer.py`.
"""

from .builder import build_brief, build_brief_direct
from .renderer import pending_due_entries, render_html

__all__ = ["build_brief", "build_brief_direct", "pending_due_entries", "render_html"]
