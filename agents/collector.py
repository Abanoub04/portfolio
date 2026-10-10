"""The Collector (Bookkeeping department): turns the raw file into clean data."""

from agents.base_agent import Agent
from tools.collector_tools import TransactionCleaner, make_collector_tools

INSTRUCTIONS = """You are the Collector in the Bookkeeping department of LedgerMind, \
a small accounting firm. Your job: turn the raw monthly transactions file into clean data.

Work only through your tools. You never change, calculate or invent numbers yourself.

Steps:
1. Load the transactions.
2. Standardize all dates to YYYY-MM-DD.
3. Set aside rows with missing or invalid amounts. Never guess an amount.
4. Remove duplicates (needs steps 2 and 3 first).
5. Save the cleaned data. Saving checks that every row is either clean or an exception.

If a tool returns an error, read it, fix the cause and continue.
When done, reply with a short summary: rows loaded, clean rows, and each exception \
(source line and issue). Report only what the tools returned."""

# What the Collector does in test mode (no API key). The first call is in
# the wrong order on purpose, to show the tool's error being handed back.
FAKE_SCRIPT = [
    {"tool": "load_transactions"},
    {"tool": "remove_duplicates"},
    {"tool": "standardize_dates"},
    {"tool": "flag_missing_amounts"},
    {"tool": "remove_duplicates"},
    {"tool": "save_cleaned_data"},
    {"text": "(test mode) Cleaning finished - see save_cleaned_data in the log for the counts."},
]

TASK = "Clean the September 2026 transactions file."


def create_collector(log, output_dir=None, source_file=None):
    cleaner = TransactionCleaner(source_file=source_file, output_dir=output_dir)
    return Agent(
        name="Collector",
        instructions=INSTRUCTIONS,
        tools=make_collector_tools(cleaner),
        log=log,
        fake_script=FAKE_SCRIPT,
    )
