"""Multi-month history: reading a previously-downloaded history CSV, merging it
with a fresh upload, and serializing the combined dataset back out.

There's no server-side database -- Streamlit Cloud's filesystem doesn't persist
across restarts anyway -- so the user holds their own running history as a file
they re-upload each time.
"""

import pandas as pd
import streamlit as st

from config import HISTORY_COLUMNS


def read_history_file(file):
    """Read a history CSV previously downloaded from this app (already in our schema).

    Trusts the stored Category as-is rather than re-running categorize_transactions,
    so manual corrections from a prior session survive the round trip.
    """
    try:
        df = pd.read_csv(file)
        df.columns = [c.strip() for c in df.columns]
        missing = [c for c in HISTORY_COLUMNS if c not in df.columns]
        if missing:
            st.warning(f"History file is missing columns ({', '.join(missing)}) and was ignored.")
            return None
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        df["AmountCharged"] = pd.to_numeric(df["AmountCharged"], errors="coerce")
        df["Debit/Credit"] = df["Debit/Credit"].astype(str).str.strip().str.capitalize()
        return df
    except Exception as e:
        st.warning(f"Could not read history file: {str(e)}")
        return None


def merge_with_history(new_df, history_df):
    """Combine a freshly-parsed statement with a prior history file, deduping by
    transaction identity. History rows win on duplicates so manual category edits
    from earlier sessions aren't clobbered by a fresh keyword-match re-run.
    """
    if history_df is None or history_df.empty:
        return new_df
    combined = pd.concat([history_df, new_df], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(
        subset=["Date", "Details", "AmountCharged", "Debit/Credit"], keep="first"
    )
    return combined.sort_values("Date").reset_index(drop=True)


def build_history_csv(debits_df, credits_df):
    """Serialize the current combined dataset back into the downloadable history format."""
    combined = pd.concat([debits_df, credits_df], ignore_index=True, sort=False)
    combined = combined.sort_values("Date")
    out = combined[HISTORY_COLUMNS].copy()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    return out.to_csv(index=False).encode("utf-8")
