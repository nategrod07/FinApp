"""Claude API access: client setup, rate limiting, and the AI-assisted features."""

import json
import threading
import time

import pandas as pd
import streamlit as st

from config import (
    AI_GLOBAL_HOURLY_LIMIT,
    AI_GLOBAL_HOURLY_WINDOW_SECONDS,
    AI_GLOBAL_MONTHLY_LIMIT,
    AI_GLOBAL_MONTHLY_WINDOW_SECONDS,
    AI_SESSION_HOURLY_LIMIT,
    AI_SESSION_HOURLY_WINDOW_SECONDS,
    CLAUDE_MODEL,
    MAX_PDF_CHARS,
)
from secrets_utils import get_secret

try:
    import anthropic
    ANTHROPIC_SDK_AVAILABLE = True
except ImportError:
    ANTHROPIC_SDK_AVAILABLE = False


@st.cache_resource
def get_claude_client():
    if not ANTHROPIC_SDK_AVAILABLE:
        return None
    api_key = get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def ai_available():
    return get_claude_client() is not None


@st.cache_resource
def _global_rate_limiter_state():
    return {"lock": threading.Lock(), "call_times": []}


def _prune_old(timestamps, window_seconds):
    cutoff = time.time() - window_seconds
    return [t for t in timestamps if t > cutoff]


def check_and_record_ai_call():
    """Enforce hourly + monthly global caps (shared across everyone on this
    deployment) plus a tighter per-session cap. Returns (allowed, message_if_blocked).
    """
    now = time.time()
    state = _global_rate_limiter_state()
    with state["lock"]:
        # Keep a full month of history; the hourly count is just a shorter-window
        # filter over the same list, so pruning here can't be done at the 1-hour
        # window or the monthly count would never see anything.
        state["call_times"] = _prune_old(state["call_times"], AI_GLOBAL_MONTHLY_WINDOW_SECONDS)
        if len(state["call_times"]) >= AI_GLOBAL_MONTHLY_LIMIT:
            return False, f"This app has hit its shared monthly AI budget ({AI_GLOBAL_MONTHLY_LIMIT}/30 days). Try again later."
        hourly_count = len(_prune_old(state["call_times"], AI_GLOBAL_HOURLY_WINDOW_SECONDS))
        if hourly_count >= AI_GLOBAL_HOURLY_LIMIT:
            return False, f"AI usage limit reached ({AI_GLOBAL_HOURLY_LIMIT} requests/hour for this app). Try again later."

        if "ai_call_times" not in st.session_state:
            st.session_state.ai_call_times = []
        st.session_state.ai_call_times = _prune_old(st.session_state.ai_call_times, AI_SESSION_HOURLY_WINDOW_SECONDS)
        if len(st.session_state.ai_call_times) >= AI_SESSION_HOURLY_LIMIT:
            return False, f"You've hit the per-session AI limit ({AI_SESSION_HOURLY_LIMIT} requests/hour). Try again later."

        state["call_times"].append(now)
        st.session_state.ai_call_times.append(now)
        return True, None


def call_claude(system_prompt, user_prompt, max_tokens=2048):
    client = get_claude_client()
    if client is None:
        return None
    allowed, block_reason = check_and_record_ai_call()
    if not allowed:
        st.error(block_reason)
        return None
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    except Exception as e:
        st.error(f"AI request failed: {str(e)}")
        return None


def extract_json_from_response(text):
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def ai_extract_transactions_from_text(raw_text):
    """Use Claude to turn raw PDF statement text into structured transactions."""
    truncated = raw_text[:MAX_PDF_CHARS]
    system_prompt = (
        "You extract bank/credit card transactions from raw statement text and output "
        "ONLY a JSON array, no markdown fences, no commentary. Each element must have keys: "
        '"date" (as written in the source), "details" (merchant/description), '
        '"amount" (positive number, no currency symbols or commas), '
        '"type" (exactly "Debit" or "Credit"). Skip headers, totals, and non-transaction lines. '
        "If you cannot find any transactions, output an empty array []."
    )
    response_text = call_claude(system_prompt, truncated, max_tokens=4096)
    if not response_text:
        return None
    data = extract_json_from_response(response_text)
    if not data:
        return None
    try:
        df = pd.DataFrame(data)
        df = df.rename(columns={
            "date": "Date", "details": "Details",
            "amount": "AmountCharged", "type": "Debit/Credit",
        })
        df["Status"] = "SETTLED"
        return df
    except Exception:
        return None


def ai_map_columns(columns, sample_rows_text):
    """Ask Claude to map a file's actual headers onto the required schema."""
    system_prompt = (
        "You map spreadsheet column headers to a required schema. Respond ONLY with a JSON "
        'object mapping each ORIGINAL header to one of "Date", "Details", "AmountCharged", '
        '"Debit/Credit", or null if it does not correspond to any of them. '
        "Use each target at most once. No markdown fences, no commentary."
    )
    user_prompt = f"Original headers: {columns}\n\nSample rows:\n{sample_rows_text}"
    response_text = call_claude(system_prompt, user_prompt, max_tokens=1024)
    if not response_text:
        return None
    mapping = extract_json_from_response(response_text)
    if not isinstance(mapping, dict):
        return None
    return {k: v for k, v in mapping.items() if v}


def ai_categorize_details(details_list, category_names):
    """Ask Claude to assign each transaction detail to an existing category."""
    system_prompt = (
        "You categorize credit card transaction descriptions into spending categories. "
        "Respond ONLY with a JSON object mapping each transaction description to exactly one "
        f"category name from this list: {category_names}. "
        'If nothing fits well, use "Uncategorized". No markdown fences, no commentary.'
    )
    user_prompt = "Transaction descriptions:\n" + "\n".join(f"- {d}" for d in details_list)
    response_text = call_claude(system_prompt, user_prompt, max_tokens=4096)
    if not response_text:
        return None
    mapping = extract_json_from_response(response_text)
    if not isinstance(mapping, dict):
        return None
    return mapping
