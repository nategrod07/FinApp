"""Turning an uploaded CSV/Excel/PDF file into a categorized transactions dataframe."""

import logging

import pandas as pd
import streamlit as st

from ai_helpers import ai_available, ai_extract_transactions_from_pdf, ai_map_columns
from config import COLUMN_ALIASES, REQUIRED_COLUMNS

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

logger = logging.getLogger(__name__)


def map_columns_with_aliases(df):
    """Rename known alias headers onto the required schema; report what's still missing."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        mapping = {}
        for alt, target in COLUMN_ALIASES.items():
            if alt in df.columns and target in missing:
                mapping[alt] = target
        df = df.rename(columns=mapping)
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    return df, missing


def clean_amount_and_type_columns(df):
    """Normalize AmountCharged to a float and Debit/Credit to consistent casing.

    The old implementation chained .str.replace(",", "") into a plain
    Series.replace("$", "", regex=True) -- since "$" is a regex end-of-string
    anchor, that second call never actually stripped dollar signs, so any
    amount written as "$1,234.56" silently became NaN and got dropped.
    """
    if df["AmountCharged"].dtype != "float":
        df["AmountCharged"] = (
            df["AmountCharged"].astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.strip()
        )
    df["AmountCharged"] = pd.to_numeric(df["AmountCharged"], errors="coerce")
    if "Debit/Credit" in df.columns:
        df["Debit/Credit"] = df["Debit/Credit"].astype(str).str.strip().str.capitalize()
    return df


def categorize_transactions(df):
    df["Category"] = "Uncategorized"
    for category, keywords in st.session_state.categories.items():
        if category == "Uncategorized" or not keywords:
            continue
        lowered_keywords = [keyword.lower().strip() for keyword in keywords]
        for idx, row in df.iterrows():
            details = str(row["Details"]).lower().strip()
            if any(keyword in details for keyword in lowered_keywords):
                df.at[idx, "Category"] = category
    return df


def clean_dates(df):
    """Fix problematic dates in the dataframe"""
    df["Original_Date"] = df["Date"].copy()

    def fix_date(date_str):
        # Try strict ISO (YYYY-MM-DD, what AI-extracted PDF dates use) first --
        # pd.to_datetime with dayfirst=True can silently swap day/month even on
        # an unambiguous ISO string when both components are <=12 (e.g.
        # "2026-03-06" -> "2026-06-03"), since dayfirst only makes sense for
        # genuinely ambiguous D/M/Y-style formats, not Y-M-D ones.
        try:
            return pd.to_datetime(date_str, format="%Y-%m-%d", errors="raise")
        except (ValueError, TypeError):
            pass
        try:
            return pd.to_datetime(date_str, errors='coerce', dayfirst=True)
        except Exception:
            return pd.NaT

    df["Date"] = df["Date"].apply(fix_date)
    if df["Original_Date"].dtype == 'object':
        mask_nov31 = df["Original_Date"].str.contains("31/11", na=False)
        if mask_nov31.any():
            fixed_dates = df.loc[mask_nov31, "Original_Date"].str.replace("31/11", "30/11")
            df.loc[mask_nov31, "Date"] = pd.to_datetime(fixed_dates, dayfirst=True, errors='coerce')
        mask_month_13plus = df["Original_Date"].str.contains(r"\d+/(?:1[3-9]|2[0-9]|3[0-9])/", na=False)
        if mask_month_13plus.any():
            fixed_dates = df.loc[mask_month_13plus, "Original_Date"].str.replace(
                r"(\d+)/(1[3-9]|2[0-9]|3[0-9])/", r"\1/12/", regex=True)
            df.loc[mask_month_13plus, "Date"] = pd.to_datetime(fixed_dates, dayfirst=True, errors='coerce')
    df["Date_formatted"] = df["Date"].dt.strftime("%m/%d/%Y")
    df.drop("Original_Date", axis=1, inplace=True)
    problem_count = df["Date"].isna().sum()
    return df, problem_count


def extract_text_from_pdf(file):
    """Extract raw text content from a PDF file"""
    try:
        pdf_reader = pypdf.PdfReader(file)
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            page_text = page.extract_text()
            if page_text:
                text += page_text
        return text
    except Exception:
        logger.exception("Failed to extract text from PDF")
        st.error("Could not read this PDF. It may be corrupted or password-protected.")
        return None


def process_pdf_file(file):
    """Process PDF files: hand the whole file to Claude's native document reading.

    No text-extraction-then-truncate step -- the PDF goes to Claude directly, so
    a long multi-page statement doesn't get silently cut off partway through.
    pypdf text extraction is still used, but only as a fallback preview when AI
    isn't available or comes back empty.
    """
    if ai_available():
        file.seek(0)
        pdf_bytes = file.read()
        with st.spinner("Using AI to read the PDF statement..."):
            df = ai_extract_transactions_from_pdf(pdf_bytes)
        if df is None or df.empty:
            st.warning("AI couldn't find recognizable transactions in this PDF.")
            if PYPDF_AVAILABLE:
                file.seek(0)
                text = extract_text_from_pdf(file)
                if text:
                    st.text_area("Extracted text preview (first 1000 characters):", text[:1000], height=200)
            return None
        st.success(f"AI extracted {len(df)} transactions from the PDF.")
        df = clean_amount_and_type_columns(df)
        df, problem_count = clean_dates(df)
        if problem_count > 0:
            st.warning(f"{problem_count} dates couldn't be parsed and were excluded.")
            df = df.dropna(subset=["Date"])
        return categorize_transactions(df)
    else:
        if not PYPDF_AVAILABLE:
            st.error("PDF processing needs either pypdf installed or an Anthropic API key configured.")
            return None
        text = extract_text_from_pdf(file)
        if not text:
            st.error("Could not extract any text from this PDF. It might be scanned or image-based.")
            return None
        st.warning("Automatic PDF parsing needs an Anthropic API key (see README for setup).")
        st.text_area("Extracted text (first 1000 characters):", text[:1000], height=200)
        st.info("You can also convert this statement to CSV/Excel and upload that instead.")
        return None


def load_transactions(file, file_type):
    """Process CSV/Excel/PDF files into a categorized transactions dataframe."""
    try:
        if file_type == "pdf":
            return process_pdf_file(file)

        if file_type == "csv":
            df = pd.read_csv(file)
        elif file_type in ["xlsx", "xls"]:
            df = pd.read_excel(file)
        else:
            st.error(f"Unsupported file type: {file_type}")
            return None

        df.columns = [col.strip() for col in df.columns]
        df, missing_columns = map_columns_with_aliases(df)

        mapping_key = f"{file.name}_{file.size}"
        if missing_columns and mapping_key in st.session_state.column_ai_mappings:
            df = df.rename(columns=st.session_state.column_ai_mappings[mapping_key])
            missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]

        if missing_columns:
            st.error(f"File is missing required columns: {', '.join(missing_columns)}")
            st.info(f"Found columns: {', '.join(df.columns)}")
            st.info("Expected columns: Date, Details, AmountCharged, Debit/Credit (or common variants).")
            if ai_available():
                if st.button("🤖 Let AI map these columns", key=f"ai_map_btn_{mapping_key}"):
                    with st.spinner("Asking AI to match your columns..."):
                        mapping = ai_map_columns(df.columns.tolist(), df.head(3).to_string())
                    if mapping:
                        st.session_state.column_ai_mappings[mapping_key] = mapping
                        st.rerun()
                    else:
                        st.error("AI couldn't confidently map these columns either.")
            else:
                st.caption("Add an Anthropic API key (see README) to let AI map unusual column names automatically.")
            return None

        df = clean_amount_and_type_columns(df)
        df, problem_count = clean_dates(df)
        if problem_count > 0:
            st.warning(f"{problem_count} dates couldn't be fixed and were set to NaT. These rows will be excluded from analysis.")
            df = df.dropna(subset=["Date"])
        return categorize_transactions(df)
    except Exception:
        logger.exception("Error processing uploaded file")
        st.error("Something went wrong processing this file. Check that it's a valid CSV/Excel/PDF export and try again.")
        return None
