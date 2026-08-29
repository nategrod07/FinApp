"""Budget Planner persistence: saved take-home-pay inputs, bills, and other
spending, so the budget survives a reload. Same on-disk JSON pattern as
category_state.py's categories.json, kept in its own file/module since the
two are unrelated data.
"""

import json
import os

BUDGET_STATE_FILE = "budget_state.json"


def load_budget_state():
    """Returns the saved budget dict, or {} if nothing's been saved yet or
    the file is unreadable (corrupt/partial write shouldn't crash the app --
    just fall back to defaults)."""
    if not os.path.exists(BUDGET_STATE_FILE):
        return {}
    try:
        with open(BUDGET_STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_budget_state(state):
    with open(BUDGET_STATE_FILE, "w") as f:
        json.dump(state, f)
