"""Central settings for LedgerMind.

Everything that might change between runs lives here, so no other file
needs to be edited to switch the model, the month, or the file paths.
The API key is NOT stored here: the Anthropic SDK reads it from the
ANTHROPIC_API_KEY environment variable.
"""

from pathlib import Path

# --- AI model -------------------------------------------------------------
# One place to change the model used by every agent.
MODEL = "claude-opus-5-5"

# How hard the model thinks before answering: "low", "medium", "high",
# "xhigh" or "max". Higher = smarter but slower and more expensive.
EFFORT = "medium"

# Maximum length of one model reply (in tokens, roughly 3/4 of a word each).
MAX_TOKENS = 16000

# Safety brake: an agent may go round its loop at most this many times
# before it is stopped. Prevents an agent from looping forever.
MAX_STEPS = 15

# --- Reporting period -----------------------------------------------------
REPORT_MONTH = "2026-09"   # September 2026
CURRENCY = "CZK"

# --- File locations (all relative to the project root) --------------------
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
OUTPUT_DIR = PROJECT_ROOT / "output"

TRANSACTIONS_FILE = DATA_DIR / "transactions.csv"
BUDGET_FILE = DATA_DIR / "budget.csv"

# Files produced by the Bookkeeping department (written to output/).
CLEAN_FILE_NAME = "transactions_clean.csv"           # Collector: clean rows
EXCEPTIONS_FILE_NAME = "exceptions.csv"              # Collector: rows set aside
CATEGORIZED_FILE_NAME = "transactions_categorized.csv"  # Categorizer

# Files produced by the Reporting department (written to output/).
ANALYSIS_FILE_NAME = f"analysis_{REPORT_MONTH}.json"  # Analyst: all the numbers
REPORT_FILE_NAME = f"report_{REPORT_MONTH}.md"        # Writer: the final report

# --- Date formats ---------------------------------------------------------
# The date formats the Collector understands, and how each is named.
# Slash dates are read day-first (DD/MM/YYYY), as is normal in Czechia.
# Every date is converted to the first one: YYYY-MM-DD.
DATE_FORMATS = {
    "%Y-%m-%d": "YYYY-MM-DD",
    "%d.%m.%Y": "DD.MM.YYYY",
    "%d/%m/%Y": "DD/MM/YYYY",
}

# --- Business rules -------------------------------------------------------
# The Analyst flags a category as unusual when actual spend is more than
# this share above budget (0.20 = 20 %).
OVER_BUDGET_THRESHOLD = 0.20

# The Analyst also flags any single expense above this amount (CZK),
# except in these categories, where large payments are normal.
LARGE_TRANSACTION_THRESHOLD = 20000
LARGE_TRANSACTION_EXCLUDED_CATEGORIES = ["Salaries", "Rent"]

# The categories the Categorizer is allowed to use.
CATEGORIES = [
    "Salaries",
    "Rent",
    "Travel",
    "Software",
    "Marketing",
    "Utilities",
    "Sales",
    "Other",
]
