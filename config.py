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

# --- Business rules -------------------------------------------------------
# The Analyst flags a category as unusual when actual spend is more than
# this share above budget (0.20 = 20 %).
OVER_BUDGET_THRESHOLD = 0.20

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
