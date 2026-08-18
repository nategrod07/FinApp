"""Secret access -- the only place that should touch st.secrets or os.environ for keys."""

import os
import streamlit as st


def get_secret(key):
    """Read a secret from st.secrets (Streamlit Cloud) or an env var (local/other hosts).

    Never hardcode secrets in source -- this is the only place that should touch
    ANTHROPIC_API_KEY or APP_PASSWORD, so a leak can only come from misconfigured
    hosting, not from this code.
    """
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key)
