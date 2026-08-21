"""APP_PASSWORD gate helpers: constant-time comparison and failed-attempt
lockout, kept separate from finapp.py so the logic is unit-testable without a
live Streamlit script run.
"""

import hmac
import threading
import time

import streamlit as st

from config import PASSWORD_LOCKOUT_WINDOW_SECONDS, PASSWORD_MAX_ATTEMPTS


@st.cache_resource
def _password_lockout_state():
    return {"lock": threading.Lock(), "failures": [], "locked_until": 0.0}


def verify_password(candidate, required):
    """Constant-time comparison so response timing can't leak the password."""
    return hmac.compare_digest(str(candidate), str(required))


def check_password_lockout():
    """Returns (is_locked, retry_after_seconds)."""
    state = _password_lockout_state()
    with state["lock"]:
        remaining = state["locked_until"] - time.time()
        return remaining > 0, max(0.0, remaining)


def record_failed_password_attempt():
    state = _password_lockout_state()
    with state["lock"]:
        now = time.time()
        state["failures"] = [t for t in state["failures"] if t > now - PASSWORD_LOCKOUT_WINDOW_SECONDS]
        state["failures"].append(now)
        if len(state["failures"]) >= PASSWORD_MAX_ATTEMPTS:
            state["locked_until"] = now + PASSWORD_LOCKOUT_WINDOW_SECONDS
            state["failures"] = []
