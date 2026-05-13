"""Shared lookup tables and status-set constants."""

GRADE_WEIGHT = {
    "HD (High Distinction)": 3,
    "D (Distinction)": 2,
    "C (Credit)": 1,
    "P (Pass)": 0,
}

GRADE_SHORT = {
    "HD (High Distinction)": "HD",
    "D (Distinction)": "D",
    "C (Credit)": "C",
    "P (Pass)": "P",
}

GRADE_COLOR = {
    "HD (High Distinction)": "#6c3483",
    "D (Distinction)":       "#1a5276",
    "C (Credit)":            "#0e6655",
    "P (Pass)":              "#784212",
}

STATUS_LABEL = {
    "not_started":        "Not Started",
    "working_on_it":      "In Progress",
    "redo_submission":    "Redo",
    "fix_and_resubmit":   "Fix & Resubmit",
    "time_exceeded":      "Overdue",
    "need_help":          "Need Help",
    "ready_for_feedback": "Submitted",
    "discuss":            "Discuss w/ Tutor",
    "demonstrate":        "Needs Demo",
    "complete":           "Complete",
    "fail":               "Failed",
}

STATUS_COLOR = {
    "not_started":        "#7f8c8d",
    "working_on_it":      "#2980b9",
    "redo_submission":    "#e74c3c",
    "fix_and_resubmit":   "#e74c3c",
    "time_exceeded":      "#c0392b",
    "need_help":          "#e67e22",
    "ready_for_feedback": "#7f8c8d",
    "discuss":            "#8e44ad",
    "demonstrate":        "#8e44ad",
    "complete":           "#27ae60",
    "fail":               "#95a5a6",
}

URGENT    = frozenset({"time_exceeded", "redo_submission", "fix_and_resubmit", "need_help"})
TODO      = frozenset({"not_started", "working_on_it"})
WAITING   = frozenset({"discuss", "demonstrate"})
SUBMITTED = frozenset({"ready_for_feedback"})
DONE      = frozenset({"complete", "fail"})
