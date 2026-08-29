# FinApp — Personal Finance Dashboard

A Streamlit app for uploading bank/credit card statements (CSV, Excel, or PDF),
auto-categorizing expenses, viewing spending trends, and planning a budget against
your take-home pay.

## Features

- Upload CSV, XLSX/XLS, or PDF statements
- Automatic column mapping for common header variants (e.g. "Description" → "Details")
- A starter set of common categories (Groceries, Dining Out, Transportation, Rent/Mortgage,
  Utilities, Healthcare, Subscriptions, Entertainment, Income, Fees & Interest, Miscellaneous)
  pre-loaded in `categories.json` so you're not starting from an empty list
- Keyword-based auto-categorization that learns as you correct it, with category icons and
  an at-a-glance metrics row (Total Spent / Total Payments / Net / Transaction count)
- Light/dark mode toggle with a custom cream-and-dark-green theme (next to the title)
- **Multi-month trends, with no database**: the Trends tab lets you download a "history" CSV
  after each upload; next time, upload your new statement plus that history file (via the
  "Merge with previous history" control) to combine them, skip duplicate transactions, and
  keep prior category corrections intact — the growing dataset lives in a file you hold, not
  on the server, so it survives restarts with no database involved. The Trends tab has
  switchable views (Total Spending / By Category) and chart types (Bar / Line / Area)
- Optional AI features (via the Claude API), each opt-in so they never run without you asking:
  - **PDF parsing** — the PDF is sent to Claude directly (native document reading, not
    extracted-then-truncated text), so multi-page statements are read in full
  - **Column mapping fallback** — maps unusual/unrecognized CSV/Excel headers
  - **Auto-categorize** — assigns categories to uncategorized transactions in one click; anything
    it isn't confident about pops up a one-at-a-time review screen where you pick an existing
    category or create a new one, instead of being silently left uncategorized
- **Budget Planner** tab (works independently of any uploaded statement):
  - Enter pay (hourly/monthly/yearly), state, and filing status for an estimated take-home
    paycheck after federal, state, and FICA taxes — a rough budgeting estimate, not tax advice
    (see `budget_data.py` for the approximation caveats)
  - List bills and fill in amounts across editable spending categories (add or remove rows
    freely) to see a pie-chart breakdown of where take-home pay goes
  - **50/30/20 preset** — one click fills in spending as 50% needs / 30% wants / 20% savings,
    crediting whatever's already in Bills against the needs share
  - **Auto-fill bills from history** — once a statement's uploaded, detects charges that repeat
    at the same merchant and amount across months (rent, insurance, subscriptions) and pre-fills
    the Bills table with them
  - **Actual vs. budgeted** — compares this budget against real categorized spending for any
    month in your uploaded history, with a variance table and chart
  - Everything here is saved automatically and reloaded next time you open the app

AI features are entirely optional. Without an API key configured, everything except
automatic PDF parsing still works exactly as before.

**A note on AI accuracy:** PDF extraction correctly infers the transaction year from the
statement period even when it isn't repeated on every row, but dollar amounts are occasionally
misread by a small margin on pages with unusual font rendering — a precision limit of the
underlying model, not something a prompt tweak fixes reliably. Spot-check AI-extracted amounts
against the source statement, especially for large or unusual transactions.

## Project structure

The app is split by responsibility instead of living in one large file:

| File | Responsibility |
|---|---|
| `finapp.py` | Entry point: page setup, password gate, the main UI layout, and the AI-categorize review dialog |
| `config.py` | Constants: AI settings, rate limits, required columns/aliases, category icons |
| `theme.py` | Light/dark palettes and the CSS/chart theming that applies them |
| `secrets_utils.py` | Reading secrets (API key, app password) from `st.secrets`/env vars |
| `category_state.py` | `categories.json` persistence and session-state init |
| `ai_helpers.py` | Claude client, rate limiter, and the AI-assisted parsing/categorizing calls |
| `parsing.py` | Turning an uploaded CSV/Excel/PDF into a categorized dataframe |
| `history.py` | Reading, merging, and exporting the multi-month history CSV |
| `budget.py` | Take-home pay estimation and budget allocation math (no Streamlit dependency) |
| `budget_data.py` | Tax brackets, state rates, and reference data for the Budget Planner |
| `budget_state.py` | Saving/loading the Budget Planner's inputs to disk between sessions |
| `auth.py` | Password-gate verification and brute-force lockout |

## Security & cost controls

- **No hardcoded secrets.** The API key is read only from Streamlit secrets or an
  environment variable (`get_secret()` in `secrets_utils.py`), never from source.
  `.streamlit/secrets.toml` is gitignored — only the placeholder `.example` file is committed.
- **Rate limiting.** Every AI call goes through a shared limiter with three caps: an hourly
  global cap (20/hour), a monthly global cap (100/30 days, so the hourly cap alone can't be
  hit repeatedly all month and blow past your budget), and a per-browser-session cap
  (10/hour). Tune `AI_GLOBAL_HOURLY_LIMIT` / `AI_GLOBAL_MONTHLY_LIMIT` / `AI_SESSION_HOURLY_LIMIT`
  in `config.py` if you want it looser or stricter. These counters live in server memory and
  reset on app reboot/sleep-wake, so they're a second line of defense — set a hard spend
  limit in the Anthropic console (Settings → Limits) as the real backstop.
- **Size/volume caps.** PDFs sent to the AI are capped by file size (`MAX_PDF_BYTES`, 15MB —
  the PDF goes in full, no text is truncated) and category suggestions are capped
  (`MAX_AI_CATEGORIZE_ITEMS`), so one huge file can't blow up a single request's cost.
- **Optional password gate.** Set `APP_PASSWORD` in secrets to require a password before
  the app loads at all — useful if you host this somewhere reachable by other people. Leave
  it unset for solo/local use. Failed attempts are rate-limited (`auth.py`) to block brute-force
  guessing.

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

To enable AI features locally, copy the secrets template and add your key:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml and paste your key
```

Get a key from [console.anthropic.com](https://console.anthropic.com/) (Settings → API Keys).
The Claude Haiku model this app uses is very cheap per request — as a safety net, you
can also set a monthly spend limit in the console under Settings → Limits.

Run it:

```bash
streamlit run finapp.py
```

## Development workflow

Changes go through a pull request, not straight to `main` — every PR runs CI (below)
and needs those checks green before it merges.

```bash
git checkout -b your-branch-name
# make changes
pip install -r requirements-dev.txt   # adds pytest/ruff/bandit/pip-audit on top of the app deps
ruff check .                          # lint
pytest tests/ -v                      # tests
git push -u origin your-branch-name
gh pr create
```

### CI checks (`.github/workflows/ci.yml`)

Runs on every PR and push to `main`:

- **Lint** — `ruff`, configured in `pyproject.toml` with a deliberately curated rule set
  (real correctness issues, import sorting, modernization — not type-hint or docstring
  requirements this codebase doesn't use)
- **Security** — `bandit` (static analysis for security issues, e.g. unsafe patterns),
  `pip-audit` (dependency vulnerability scan, advisory-only since this app pins no
  transitive versions and findings in packages pulled in by streamlit/pandas shift with
  every install), and a grep-based check that no API key or `.streamlit/secrets.toml`
  ever gets committed
- **Tests** — `pytest`, covering the parsing/date/history/rate-limiter logic (`tests/`)
- **Boot smoke test** — since this is a server-rendered Streamlit app with no separate
  JS frontend, "does the UI build" means "does the app actually boot and respond,"
  which this checks directly
