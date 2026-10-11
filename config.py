"""Central settings for LedgerMind.

Everything that might change between runs lives here, so no other file
needs to be edited to switch the model, the month, or the file paths.
The API key is NOT stored here: the Anthropic SDK reads it from the
ANTHROPIC_API_KEY environment variable.
"""

import os
from pathlib import Path

# --- API key from a .env file (optional) ----------------------------------
# The Anthropic API key is never written in code. It is read from the
# environment variable ANTHROPIC_API_KEY. For convenience it can also be put
# in a file called .env in the project root (see .env.example); that file is
# listed in .gitignore, so it is never committed.


def load_env_file(path):
    """Read KEY=value lines from a .env file into the environment.
    A variable that is already set is never overwritten."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(Path(__file__).parent / ".env")

# --- AI model -------------------------------------------------------------
# One place to change the model used by every agent.
# Claude Opus 5.5: Anthropic's current default model for agent work - strong
# at following strict rules (cite your sources, never invent numbers) and at
# judging unclear transactions. $4 / $20 per million input / output tokens;
# one full run costs roughly $1 (see README.md).
# Cheaper options: "claude-sonnet-5-5" (about half the price) or
# "claude-haiku-5-5" (much cheaper, weaker judgement).
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
DRAFT_REPORT_FILE_NAME = f"draft_report_{REPORT_MONTH}.md"  # Writer: draft for review

# Files produced by the Manager (written to output/).
REPORT_FILE_NAME = f"report_{REPORT_MONTH}.md"              # the delivered report
REVIEW_NOTES_FILE_NAME = f"review_notes_{REPORT_MONTH}.md"  # what was checked
ESCALATION_FILE_NAME = f"escalation_{REPORT_MONTH}.md"      # only if not delivered
RUN_CHECK_FILE_NAME = f"run_check_{REPORT_MONTH}.md"        # hard checks + soft differences

# How many times the Manager may send the report back to the Writer
# before it must stop and escalate to the owner.
MAX_REVISIONS = 2

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
