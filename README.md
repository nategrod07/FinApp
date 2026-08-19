# FinApp — Personal Finance Dashboard

A Streamlit app for uploading bank/credit card statements (CSV, Excel, or PDF),
auto-categorizing expenses, and viewing spending summaries.

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
  on the server, so it works even though Streamlit Cloud's filesystem doesn't persist. The
  Trends tab has switchable views (Total Spending / By Category) and chart types (Bar / Line /
  Area)
- Optional AI features (via the Claude API), each opt-in so they never run without you asking:
  - **PDF parsing** — the PDF is sent to Claude directly (native document reading, not
    extracted-then-truncated text), so multi-page statements are read in full
  - **Column mapping fallback** — maps unusual/unrecognized CSV/Excel headers
  - **Auto-categorize** — assigns categories to uncategorized transactions in one click; anything
    it isn't confident about pops up a one-at-a-time review screen where you pick an existing
    category or create a new one, instead of being silently left uncategorized

AI features are entirely optional. Without an API key configured, everything except
automatic PDF parsing still works exactly as before.

**A note on AI accuracy:** in testing against a real 4-page statement, PDF extraction correctly
read the year for every transaction (inferred from the statement period, since the year isn't
repeated on each row) and got 43 of 45 dollar amounts exactly right — but misread two amounts
by a small margin on a page with unusual font rendering. This is a reading-precision limit of
the underlying model, not something a prompt tweak fixes reliably. Spot-check AI-extracted
amounts against the source statement, especially for large or unusual transactions.

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
  the app loads at all — useful once you deploy to a public URL, since Streamlit Community
  Cloud apps on the free tier are reachable by anyone with the link. Leave it unset for
  solo/local use.
- Set a spend limit in the [Anthropic console](https://console.anthropic.com/) (Settings →
  Limits) as a backstop regardless of the above.

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

## Deploying (Streamlit Community Cloud)

> Note: if you've been running this inside a GitHub Codespace, that's a dev environment,
> not a deployment — it pauses when you're not actively connected, which is why the app
> "goes down" after you log off. Deploying to Streamlit Community Cloud runs independently
> of your machine.

1. Push this repo to GitHub (already done if you're reading this from the repo).
2. Go to [share.streamlit.io](https://share.streamlit.io/) and sign in with GitHub.
3. Click **New app**, pick this repo/branch, and set the main file to `finapp.py`.
4. Before or after deploying, open the app's **Settings → Secrets** and add:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   (Skip this if you don't want AI features live — the app runs fine without it.)
5. Deploy. The app stays up independently of your computer.

Free-tier apps on Streamlit Community Cloud sleep after about 7 days with zero visitors
(one click to wake them back up) — this is different from "shuts off when I log off,"
which was the Codespaces behavior. There is no fully-free host with zero sleep at all for
a managed Streamlit app; the only real way to get that is running it yourself on an
always-on free VM (e.g. an Oracle Cloud "Always Free" instance), which trades the sleep
issue for doing your own server administration.

## Known limitation: category keywords aren't persistent on the cloud

`categories.json` is read/written as a local file. That works for local development, but
Streamlit Community Cloud's filesystem resets on every redeploy/restart, so keywords learned
through the UI (via manual category corrections or the AI auto-categorize button) won't
survive one — you'd start back at the committed starter categories after a restart.

This is different from transaction *history*, which now persists via the download/re-upload
history-file workflow described above (that data lives in a file on your machine, so it's
unaffected by the server resetting). Only the learned keyword list is still server-local.
Worth revisiting later (e.g. a small hosted database) if the repeated re-learning gets
annoying.
