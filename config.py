"""App-wide constants: AI settings, rate limits, and parsing/category reference data."""

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
# PDFs go to Claude as a native document (no character-count truncation); this
# is just a sanity/cost cap on file size, well above any real bank statement.
MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_AI_CATEGORIZE_ITEMS = 200

# AI calls cost real money. Three caps apply together:
# - an hourly global cap: stops a burst (bug loop, scripted abuse) in its tracks
# - a monthly global cap: bounds worst-case spend even if the hourly cap gets hit
#   over and over across a whole month -- the hourly cap alone doesn't do this
# - a per-session cap: keeps one browser session from using the whole budget itself
# These live in server memory and reset on app reboot/sleep-wake, so they're a
# second line of defense -- set a hard spend limit in the Anthropic console
# (Settings -> Limits) as the real backstop.
AI_GLOBAL_HOURLY_LIMIT = 20
AI_GLOBAL_HOURLY_WINDOW_SECONDS = 3600
AI_GLOBAL_MONTHLY_LIMIT = 100
AI_GLOBAL_MONTHLY_WINDOW_SECONDS = 30 * 24 * 3600
AI_SESSION_HOURLY_LIMIT = 10
AI_SESSION_HOURLY_WINDOW_SECONDS = 3600

# APP_PASSWORD brute-force protection: lock out further attempts for a window
# after this many wrong guesses. Tracked globally (server-wide, not per-IP --
# see auth.py), which is a coarse defense appropriate for a small solo/shared
# deployment: it stops scripted guessing, at the cost of one attacker's flood
# also locking out the legitimate owner for the window.
PASSWORD_MAX_ATTEMPTS = 5
PASSWORD_LOCKOUT_WINDOW_SECONDS = 15 * 60

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
