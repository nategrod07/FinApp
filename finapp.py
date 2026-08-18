
import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
import time
import threading

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_SDK_AVAILABLE = True
except ImportError:
    ANTHROPIC_SDK_AVAILABLE = False

st.set_page_config(page_title="FinApp", page_icon="💰", layout="wide")

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_PDF_CHARS = 15000
MAX_AI_CATEGORIZE_ITEMS = 200

# AI calls cost real money. Three caps apply together:
# - an hourly global cap: stops a burst (bug loop, scripted abuse) in its tracks
# - a monthly global cap: bounds worst-case spend even if the hourly cap gets hit
#   over and over across a whole month -- the hourly cap alone doesn't do this
# - a per-session cap: keeps one browser session from using the whole budget itself
# These live in server memory and reset on app reboot/sleep-wake, so they're a
# second line of defense -- set a hard spend limit in the Anthropic console
# (Settings -> Limits) as the real backstop.
AI_GLOBAL_HOURLY_LIMIT = 10
AI_GLOBAL_HOURLY_WINDOW_SECONDS = 3600
AI_GLOBAL_MONTHLY_LIMIT = 100
AI_GLOBAL_MONTHLY_WINDOW_SECONDS = 30 * 24 * 3600
AI_SESSION_HOURLY_LIMIT = 5
AI_SESSION_HOURLY_WINDOW_SECONDS = 3600

REQUIRED_COLUMNS = ["Date", "Details", "AmountCharged", "Debit/Credit"]

COLUMN_ALIASES = {
    "Transaction Date": "Date",
    "TransactionDate": "Date",
    "Date of Transaction": "Date",
    "Tx Date": "Date",
    "Posting Date": "Date",
    "Description": "Details",
    "Merchant": "Details",
    "Transaction": "Details",
    "Payee": "Details",
    "Memo": "Details",
    "Amount": "AmountCharged",
    "Value": "AmountCharged",
    "Transaction Amount": "AmountCharged",
    "Type": "Debit/Credit",
    "Transaction Type": "Debit/Credit",
}

CATEGORY_ICONS = {
    "uncategorized": "❓",
    "groceries": "🛒",
    "dining out": "🍽️",
    "eating out": "🍽️",
    "transportation": "⛽",
    "rent/mortgage": "🏠",
    "utilities": "💡",
    "insurance": "🛡️",
    "healthcare": "🏥",
    "subscriptions": "📺",
    "shopping": "🛍️",
    "travel": "✈️",
    "entertainment": "🎬",
    "income": "💰",
    "fees & interest": "💳",
    "miscellaneous": "📦",
}
DEFAULT_CATEGORY_ICON = "🏷️"

HISTORY_COLUMNS = ["Date", "Details", "AmountCharged", "Debit/Credit", "Category"]


def category_icon(category):
    return CATEGORY_ICONS.get(str(category).strip().lower(), DEFAULT_CATEGORY_ICON)


# --- Theme ---------------------------------------------------------------
# Streamlit's config.toml only expresses one static theme, so a runtime
# light/dark toggle needs its own CSS injected over the top. config.toml is
# still set to match the light palette below, since that's what paints
# before any session state (and this CSS) exists on first load.

LIGHT_PALETTE = {
    "bg": "#FBF7EE",
    "surface": "#F3ECD9",
    "primary": "#1B4332",
    "primary_light": "#2D6A4F",
    "text": "#26261F",
    "text_muted": "#5C5A4E",
    "border": "#E2D5B7",
    "plotly_template": "plotly_white",
    "chart_colors": ["#1B4332", "#2D6A4F", "#40916C", "#52B788", "#74C69D", "#95D5B2", "#B7E4C7", "#D8F3DC"],
}
DARK_PALETTE = {
    "bg": "#12201A",
    "surface": "#1B2B22",
    "primary": "#52B788",
    "primary_light": "#74C69D",
    "text": "#F1EAD9",
    "text_muted": "#B7C4B9",
    "border": "#2C3F32",
    "plotly_template": "plotly_dark",
    "chart_colors": ["#95D5B2", "#74C69D", "#52B788", "#40916C", "#B7E4C7", "#D8F3DC", "#2D6A4F", "#B7E4C7"],
}


def apply_theme_css(palette):
    st.markdown(f"""
    <style>
    .stApp {{
        background-color: {palette['bg']};
        color: {palette['text']};
    }}
    [data-testid="stHeader"] {{
        background-color: transparent;
    }}
    [data-testid="stSidebar"],
    [data-testid="stMetric"],
    [data-testid="stExpander"],
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: {palette['surface']};
        border-radius: 12px;
        border: 1px solid {palette['border']};
    }}
    [data-testid="stFileUploaderDropzoneInstructions"] span,
    [data-testid="stFileUploaderDropzoneInstructions"] small,
    [data-testid="stFileUploaderDropzoneInstructions"] svg {{
        color: {palette['text_muted']} !important;
        fill: {palette['text_muted']} !important;
    }}
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
        border: 1px solid {palette['border']};
        border-radius: 8px;
    }}
    [data-testid="stMetric"] {{
        padding: 1rem;
    }}
    h1, h2, h3, h4, p, span, label, div, .stMarkdown {{
        color: {palette['text']};
    }}
    [data-testid="stMetricValue"] {{
        color: {palette['text']} !important;
    }}
    [data-testid="stMetricLabel"] {{
        color: {palette['text_muted']} !important;
    }}
    [data-testid^="stBaseButton"] {{
        border-radius: 8px !important;
        border: 1px solid {palette['primary']} !important;
        background-color: {palette['surface']} !important;
        color: {palette['text']} !important;
    }}
    [data-testid="stBaseButton-primary"] {{
        background-color: {palette['primary']} !important;
        color: {palette['bg']} !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        color: {palette['text_muted']};
    }}
    .stTabs [aria-selected="true"] {{
        color: {palette['primary']};
    }}
    /* The selectbox's own background is locked to Streamlit's static (light)
       config.toml theme regardless of this toggle, so fighting it to go dark
       just reintroduces invisible text -- instead pin its text dark so it
       always reads against that permanently-light background. */
    [data-baseweb="select"] * {{
        color: {LIGHT_PALETTE['text']} !important;
    }}
    [data-baseweb="popover"], [data-baseweb="menu"], [role="option"] {{
        background-color: {LIGHT_PALETTE['surface']} !important;
        color: {LIGHT_PALETTE['text']} !important;
    }}
    [data-testid="stTextInput"] input, [data-testid="stTextInput"] div {{
        background-color: {palette['surface']} !important;
        color: {palette['text']} !important;
    }}
    </style>
    """, unsafe_allow_html=True)


def themed_chart(fig, palette, height=380):
    fig.update_layout(
        template=palette["plotly_template"],
        paper_bgcolor=palette["surface"],
        plot_bgcolor=palette["surface"],
        font_color=palette["text"],
        title_font_color=palette["text"],
        legend_font_color=palette["text"],
        height=height,
        margin=dict(t=40, b=20, l=20, r=20),
    )
    return fig


# Session state setup
category_file = "categories.json"
if "categories" not in st.session_state:
    st.session_state.categories = {
        "Uncategorized": [],
    }
if "column_ai_mappings" not in st.session_state:
    st.session_state.column_ai_mappings = {}
if "manual_categorize_queue" not in st.session_state:
    st.session_state.manual_categorize_queue = []

if os.path.exists(category_file):
    with open(category_file, "r") as f:
        st.session_state.categories = json.load(f)


def save_categories():
    with open(category_file, "w") as f:
        json.dump(st.session_state.categories, f)


# --- Secrets & access control -------------------------------------------

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


def check_app_password():
    """Optional gate: if APP_PASSWORD is set in secrets, require it before showing the app.

    Off by default (no secret configured = no prompt), so local/solo use is unaffected.
    This exists to stop random visitors to a public deployment URL from burning your
    AI budget or viewing your uploaded financial data.
    """
    required = get_secret("APP_PASSWORD")
    if not required:
        return True
    if st.session_state.get("app_authed"):
        return True
    st.title("FinApp")
    pw = st.text_input("Enter app password", type="password")
    if pw:
        if pw == required:
            st.session_state.app_authed = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False


# --- AI helpers -------------------------------------------------------

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


# --- Parsing helpers ----------------------------------------------------

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


def clean_dates(df):
    """Fix problematic dates in the dataframe"""
    df["Original_Date"] = df["Date"].copy()

    def fix_date(date_str):
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
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            page_text = page.extract_text()
            if page_text:
                text += page_text
        return text
    except Exception as e:
        st.error(f"Failed to extract text from PDF: {str(e)}")
        return None


def process_pdf_file(file):
    """Process PDF files: pull text out, then let Claude structure it into transactions."""
    if not PYPDF2_AVAILABLE:
        st.error("PDF processing is not available. Please install PyPDF2.")
        return None
    text = extract_text_from_pdf(file)
    if not text:
        st.error("Could not extract any text from this PDF. It might be scanned or image-based.")
        return None

    if ai_available():
        with st.spinner("Using AI to read the PDF statement..."):
            df = ai_extract_transactions_from_text(text)
        if df is None or df.empty:
            st.warning("AI couldn't find recognizable transactions in this PDF.")
            st.text_area("Extracted text (first 1000 characters):", text[:1000], height=200)
            return None
        st.success(f"AI extracted {len(df)} transactions from the PDF.")
        df = clean_amount_and_type_columns(df)
        df, problem_count = clean_dates(df)
        if problem_count > 0:
            st.warning(f"{problem_count} dates couldn't be parsed and were excluded.")
            df = df.dropna(subset=["Date"])
        return categorize_transactions(df)
    else:
        st.warning("Automatic PDF parsing needs an Anthropic API key (see README for setup).")
        st.text_area("Extracted text (first 1000 characters):", text[:1000], height=200)
        st.info("You can also convert this statement to CSV/Excel and upload that instead.")
        return None


def add_keyword_to_category(category, keyword):
    keyword = keyword.strip()
    if not category in st.session_state.categories:
        st.session_state.categories[category] = []
    if keyword and keyword not in st.session_state.categories[category]:
        st.session_state.categories[category].append(keyword)
        save_categories()
        return True
    return False


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
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None


def _clear_manual_categorize_widgets():
    for k in ["manual_cat_mode", "manual_cat_existing", "manual_cat_new"]:
        st.session_state.pop(k, None)


@st.dialog("Categorize this transaction")
def categorize_dialog():
    if not st.session_state.manual_categorize_queue:
        return
    item = st.session_state.manual_categorize_queue[0]
    remaining = len(st.session_state.manual_categorize_queue)
    st.write(f"**{item['details']}**")
    st.caption(f"${item['amount']:,.2f} · {remaining} transaction{'s' if remaining != 1 else ''} left to review")

    existing_categories = [c for c in st.session_state.categories.keys() if c != "Uncategorized"]
    mode = st.radio("Assign to:", ["Existing category", "New category"], horizontal=True, key="manual_cat_mode")
    if mode == "Existing category":
        chosen = st.selectbox("Category", options=existing_categories, key="manual_cat_existing")
    else:
        chosen = st.text_input("New category name", key="manual_cat_new").strip()

    col_skip, col_save = st.columns(2)
    with col_skip:
        if st.button("Skip", use_container_width=True):
            _clear_manual_categorize_widgets()
            st.session_state.manual_categorize_queue.pop(0)
            st.rerun()
    with col_save:
        if st.button("Save", type="primary", use_container_width=True):
            if not chosen:
                st.warning("Pick or name a category first.")
            else:
                if chosen not in st.session_state.categories:
                    st.session_state.categories[chosen] = []
                matches = st.session_state.debits_df["Details"] == item["details"]
                st.session_state.debits_df.loc[matches, "Category"] = chosen
                add_keyword_to_category(chosen, item["details"])
                _clear_manual_categorize_widgets()
                st.session_state.manual_categorize_queue.pop(0)
                st.rerun()


def main():
    if not check_app_password():
        return

    dark_mode = st.session_state.get("dark_mode_toggle", False)
    palette = DARK_PALETTE if dark_mode else LIGHT_PALETTE
    apply_theme_css(palette)

    col_title, col_toggle = st.columns([5, 1])
    with col_title:
        st.title("💰 Personal Finance Dashboard")
    with col_toggle:
        st.write("")
        st.toggle("🌙 Dark", key="dark_mode_toggle")

    with st.container(border=True):
        col_upload, col_history = st.columns([3, 2])
        with col_upload:
            uploaded_file = st.file_uploader(
                "Upload your transaction or bank statement file",
                type=["csv", "xlsx", "xls", "pdf"]
            )
        with col_history:
            with st.expander("📎 Merge with previous history (optional)"):
                st.caption(
                    "Have a history file downloaded from this app before? Upload it to combine "
                    "with the new statement and build a trend over time -- no account needed, "
                    "you just hang on to the file."
                )
                history_file = st.file_uploader(
                    "History CSV", type=["csv"], key="history_uploader", label_visibility="collapsed"
                )

    if uploaded_file is not None:
        file_type = uploaded_file.name.split(".")[-1].lower()
        st.info(f"Processing {file_type.upper()} file: {uploaded_file.name}")
        df = load_transactions(uploaded_file, file_type)
        if df is not None:
            if history_file is not None:
                history_df = read_history_file(history_file)
                if history_df is not None:
                    new_count = len(df)
                    df = merge_with_history(df, history_df)
                    st.success(f"Merged with history: {len(df)} total transactions ({new_count} from this upload).")

            debits_df = df[df["Debit/Credit"] == "Debit"].copy()
            credits_df = df[df["Debit/Credit"] == "Credit"].copy()
            st.session_state.debits_df = debits_df.copy()

            if st.session_state.manual_categorize_queue:
                categorize_dialog()

            with st.container(border=True):
                metric_cols = st.columns(4)
                metric_cols[0].metric("Total Spent", f"${debits_df['AmountCharged'].sum():,.2f}")
                metric_cols[1].metric("Total Payments", f"${credits_df['AmountCharged'].sum():,.2f}")
                metric_cols[2].metric("Net", f"${credits_df['AmountCharged'].sum() - debits_df['AmountCharged'].sum():,.2f}")
                metric_cols[3].metric("Transactions", f"{len(df):,}")

            tab1, tab2, tab3 = st.tabs(["💸 Expenses (Debits)", "💵 Payments (Credits)", "📈 Trends"])
            with tab1:
                with st.container(border=True):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        new_category = st.text_input("New category Name")
                        add_button = st.button("Add Category", use_container_width=True)
                        if add_button and new_category:
                            if new_category not in st.session_state.categories:
                                st.session_state.categories[new_category] = []
                                save_categories()
                                st.rerun()
                    with col_b:
                        if ai_available():
                            st.write("Let AI sort your uncategorized expenses:")
                            if st.button("🤖 Auto-categorize with AI", use_container_width=True):
                                uncategorized = sorted(
                                    st.session_state.debits_df.loc[
                                        st.session_state.debits_df["Category"] == "Uncategorized", "Details"
                                    ].dropna().unique().tolist()
                                )
                                if not uncategorized:
                                    st.info("Nothing to categorize — everything already has a category.")
                                else:
                                    capped = uncategorized[:MAX_AI_CATEGORIZE_ITEMS]
                                    with st.spinner(f"Asking AI to categorize {len(capped)} transactions..."):
                                        mapping = ai_categorize_details(capped, list(st.session_state.categories.keys()))
                                    if mapping:
                                        applied = 0
                                        unresolved = []
                                        for detail in capped:
                                            category = mapping.get(detail, "Uncategorized")
                                            if category == "Uncategorized" or category not in st.session_state.categories:
                                                unresolved.append(detail)
                                                continue
                                            matches = st.session_state.debits_df["Details"] == detail
                                            st.session_state.debits_df.loc[matches, "Category"] = category
                                            add_keyword_to_category(category, detail)
                                            applied += 1
                                        if unresolved:
                                            queue_items = []
                                            for detail in unresolved:
                                                amt_matches = st.session_state.debits_df.loc[
                                                    st.session_state.debits_df["Details"] == detail, "AmountCharged"
                                                ]
                                                amount = amt_matches.iloc[0] if not amt_matches.empty else 0
                                                queue_items.append({"details": detail, "amount": amount})
                                            st.session_state.manual_categorize_queue = queue_items
                                        st.success(
                                            f"AI categorized {applied} transaction(s). "
                                            f"{len(unresolved)} need your input."
                                        )
                                        st.rerun()
                                    else:
                                        st.error("AI categorization failed. Try again in a moment.")

                with st.container(border=True):
                    st.subheader("Your Expenses")
                    edited_df = st.data_editor(
                        st.session_state.debits_df[["Date", "Details", "AmountCharged", "Category"]],
                        column_config={
                            "Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY"),
                            "AmountCharged": st.column_config.NumberColumn("AmountCharged", format="%.2f USD"),
                            "Category": st.column_config.SelectboxColumn(
                                "Category",
                                options=list(st.session_state.categories.keys())
                            )
                        },
                        hide_index=True,
                        use_container_width=True,
                        key="category_editor"
                    )
                    save_button = st.button("Apply Changes", type="primary")
                    if save_button:
                        for idx, row in edited_df.iterrows():
                            new_category = row["Category"]
                            if new_category == st.session_state.debits_df.at[idx, "Category"]:
                                continue
                            details = row["Details"]
                            st.session_state.debits_df.at[idx, "Category"] = new_category
                            add_keyword_to_category(new_category, details)

                with st.container(border=True):
                    st.subheader('Expense Summary')
                    category_totals = st.session_state.debits_df.groupby("Category")["AmountCharged"].sum().reset_index()
                    category_totals = category_totals.sort_values("AmountCharged", ascending=False)
                    category_totals["Category"] = category_totals["Category"].apply(
                        lambda c: f"{category_icon(c)} {c}"
                    )
                    col_table, col_chart = st.columns(2)
                    with col_table:
                        st.dataframe(
                            category_totals,
                            column_config={
                                "AmountCharged": st.column_config.NumberColumn("AmountCharged", format="%.2f USD")
                            },
                            use_container_width=True,
                            hide_index=True
                        )
                    with col_chart:
                        fig = px.pie(
                            category_totals,
                            values="AmountCharged",
                            names="Category",
                            title="Expenses by Category",
                            color_discrete_sequence=palette["chart_colors"]
                        )
                        st.plotly_chart(themed_chart(fig, palette), use_container_width=True)
            with tab2:
                with st.container(border=True):
                    st.subheader("Payment Summary")
                    total_payments = credits_df["AmountCharged"].sum()
                    st.metric("Total payments", f"{total_payments:,.2f} USD")
                    st.dataframe(credits_df, use_container_width=True, hide_index=True)
            with tab3:
                with st.container(border=True):
                    st.subheader("Spending Trends")
                    trend_source = st.session_state.debits_df
                    if trend_source.empty:
                        st.info("No expense data to chart yet.")
                    else:
                        col_view, col_chart_type = st.columns(2)
                        with col_view:
                            view = st.radio(
                                "View", ["Total Spending", "By Category"], horizontal=True, key="trend_view"
                            )
                        with col_chart_type:
                            chart_type = st.radio(
                                "Chart type", ["Bar", "Line", "Area"], horizontal=True, key="trend_chart_type"
                            )

                        trend_df = trend_source.copy()
                        trend_df["Month"] = trend_df["Date"].dt.to_period("M").astype(str)

                        if len(trend_df["Month"].unique()) < 2:
                            st.caption(
                                "Only one month of data so far — download your history below and merge it back "
                                "in next time you upload a statement to build a real trend."
                            )

                        chart_fn = {"Bar": px.bar, "Line": px.line, "Area": px.area}[chart_type]
                        if view == "Total Spending":
                            monthly_totals = trend_df.groupby("Month")["AmountCharged"].sum().reset_index().sort_values("Month")
                            fig_trend = chart_fn(
                                monthly_totals, x="Month", y="AmountCharged",
                                title="Monthly Spending",
                                labels={"AmountCharged": "Total Spent ($)"},
                                color_discrete_sequence=palette["chart_colors"]
                            )
                        else:
                            cat_trend = trend_df.groupby(["Month", "Category"])["AmountCharged"].sum().reset_index().sort_values("Month")
                            chart_kwargs = {"color": "Category"}
                            if chart_type == "Bar":
                                chart_kwargs["barmode"] = "stack"
                            fig_trend = chart_fn(
                                cat_trend, x="Month", y="AmountCharged",
                                title="Monthly Spending by Category",
                                labels={"AmountCharged": "Total Spent ($)"},
                                color_discrete_sequence=palette["chart_colors"],
                                **chart_kwargs
                            )
                        st.plotly_chart(themed_chart(fig_trend, palette), use_container_width=True)

                with st.container(border=True):
                    st.subheader("Save Your History")
                    st.caption(
                        "Download this combined, categorized dataset. Next time you're back, upload it again "
                        "under \"Merge with previous history\" above along with your new statement -- that's "
                        "how this app keeps a running history without needing its own database."
                    )
                    history_csv = build_history_csv(st.session_state.debits_df, credits_df)
                    st.download_button(
                        "⬇️ Download updated history (CSV)",
                        data=history_csv,
                        file_name="finapp_history.csv",
                        mime="text/csv"
                    )
    with st.expander("Help & Instructions"):
        ai_status = "enabled" if ai_available() else "not configured (add an API key to enable it, see README)"
        st.markdown(f"""
        ### Supported File Types
        - **CSV**: Standard comma-separated values files with transaction data
        - **Excel**: Both .xlsx and .xls formats with transaction data
        - **PDF**: Text is pulled from the PDF and, when AI is enabled, structured into transactions automatically

        ### Required Columns
        Your file should have these columns (or a common variant, which is auto-mapped):
        - **Date**: Transaction date
        - **Details**: Description of the transaction
        - **AmountCharged**: Transaction amount
        - **Debit/Credit**: Indicates whether it's an expense (Debit) or payment (Credit)

        ### AI-assisted features (status: {ai_status})
        - **PDF extraction**: reads unstructured statement text and turns it into transaction rows
        - **Column mapping**: when a CSV/Excel file has unrecognized headers, AI can map them for you
        - **Auto-categorize**: assigns categories to uncategorized transactions in one click. Anything AI
          isn't confident about pops up as a quick "categorize this" screen instead of being left alone,
          where you can assign an existing category or create a new one on the spot.

        ### Building a history across months
        This app doesn't store anything on a server between sessions. Instead, the **Trends** tab lets
        you download a "history" CSV after each upload. Next time you come back, upload your new
        statement as usual, then also drop that history file into **"Merge with previous history"**
        above the uploader -- it combines both, skips duplicate transactions, and keeps your category
        corrections intact so trends build up over time.

        ### Starter categories
        A set of common categories (Groceries, Dining Out, Transportation, Rent/Mortgage, Utilities,
        Healthcare, Subscriptions, Entertainment, Income, Fees & Interest, Miscellaneous) comes
        pre-loaded so you're not starting from a blank list -- add, rename, or ignore any of them.

        ### Light / dark mode
        Use the toggle next to the title to switch themes.
        """)


if __name__ == "__main__":
    main()
