# FinApp — Personal Finance Dashboard

A Streamlit app for uploading bank/credit card statements (CSV, Excel, or PDF),
auto-categorizing expenses, and viewing spending summaries.

## Features

- Upload CSV, XLSX/XLS, or PDF statements
- Automatic column mapping for common header variants (e.g. "Description" → "Details")
- Keyword-based auto-categorization that learns as you correct it
- Optional AI features (via the Claude API), each opt-in so they never run without you asking:
  - **PDF parsing** — reads unstructured statement text and extracts transactions
  - **Column mapping fallback** — maps unusual/unrecognized CSV/Excel headers
  - **Auto-categorize** — assigns categories to uncategorized transactions in one click

AI features are entirely optional. Without an API key configured, everything except
automatic PDF parsing still works exactly as before.

## Security & cost controls

- **No hardcoded secrets.** The API key is read only from Streamlit secrets or an
  environment variable (`get_secret()` in `finapp.py`), never from source. `.streamlit/secrets.toml`
  is gitignored — only the placeholder `.example` file is committed.
- **Rate limiting.** Every AI call goes through a shared limiter with three caps: an hourly
  global cap (10/hour), a monthly global cap (100/30 days, so the hourly cap alone can't be
  hit repeatedly all month and blow past your budget), and a per-browser-session cap
  (5/hour). Tune `AI_GLOBAL_HOURLY_LIMIT` / `AI_GLOBAL_MONTHLY_LIMIT` / `AI_SESSION_HOURLY_LIMIT`
  in `finapp.py` if you want it looser or stricter. These counters live in server memory and
  reset on app reboot/sleep-wake, so they're a second line of defense — set a hard spend
  limit in the Anthropic console (Settings → Limits) as the real backstop.
- **Input truncation.** PDF text sent to the AI is capped (`MAX_PDF_CHARS`) and category
  suggestions are capped (`MAX_AI_CATEGORIZE_ITEMS`), so one huge file can't blow up a
  single request's cost.
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

## Known limitation: storage is not persistent on the cloud

`categories.json` is read/written as a local file. That works for local development, but
Streamlit Community Cloud's filesystem resets on every redeploy/restart, so categories
learned through the UI won't survive one. This wasn't part of the current fix — worth
revisiting later (e.g. moving categories/transactions into a small hosted database) if you
want history to persist across sessions on the cloud.
