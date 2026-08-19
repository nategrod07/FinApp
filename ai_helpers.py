"""Claude API access: client setup, rate limiting, and the AI-assisted features."""

import base64
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
    MAX_PDF_BYTES,
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


def _call_claude_raw(system_prompt, content, max_tokens=2048):
    """Shared call path for both plain-text prompts and document (PDF) input.

    `content` is either a string or a list of content blocks (e.g. a PDF document
    block plus an instruction block). Rate limiting lives here so every AI-calling
    function -- text or document -- goes through the same shared budget.
    """
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
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text
    except Exception as e:
        st.error(f"AI request failed: {str(e)}")
        return None


def call_claude(system_prompt, user_prompt, max_tokens=2048):
    return _call_claude_raw(system_prompt, user_prompt, max_tokens=max_tokens)


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


def ai_extract_transactions_from_pdf(pdf_bytes):
    """Send the PDF straight to Claude's native document understanding.

    This reads the whole file -- there's no character-count cutoff the way there
    was extracting text via PyPDF2 first and truncating it, so multi-page
    statements aren't silently cut off partway through. It also tends to read
    tables/layout more accurately than flattened extracted text. The PDF still
    only ever goes to the same Anthropic API endpoint already used for every
    other AI feature here -- no new third party, same trust boundary as before.
    """
    if len(pdf_bytes) > MAX_PDF_BYTES:
        st.error(
            f"PDF is too large for AI extraction ({len(pdf_bytes) / 1_048_576:.1f}MB, "
            f"limit {MAX_PDF_BYTES // 1_048_576}MB). Try splitting it or converting to CSV/Excel."
        )
        return None
    system_prompt = (
        "You extract bank/credit card transactions from a statement PDF and output "
        "ONLY a JSON array, no markdown fences, no commentary. Each element must have keys: "
        '"date" as a full date in YYYY-MM-DD format, "details" (merchant/description), '
        '"amount" (positive number, no currency symbols or commas), '
        '"type" (exactly "Debit" or "Credit"). Skip headers, totals, and non-transaction lines. '
        "Read every page. If you cannot find any transactions, output an empty array []. "
        "Statements commonly print each transaction row with only a month and day (e.g. "
        '"03/16") and state the year once elsewhere, in a statement period near the top '
        '(e.g. "February 20, 2026 through March 18, 2026"). When a row has no year, infer '
        "it from that statement period -- never invent a placeholder year. If the period "
        "spans a year boundary (e.g. December into January), match each transaction's year "
        "to whichever side of the boundary its month actually falls on, not just the "
        "period's start year."
    )
    content = [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(pdf_bytes).decode("utf-8"),
            },
        },
        {"type": "text", "text": "Extract all transactions from this statement."},
    ]
    response_text = _call_claude_raw(system_prompt, content, max_tokens=8192)
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
