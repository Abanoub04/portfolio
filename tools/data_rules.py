"""Data-quality rules shared by the Collector, the Categorizer and the Manager.

Keeping them in one place means the department that applies a rule and the
Manager who checks it use exactly the same definition. None of these rules
uses an answer key, so they work on any client file.
"""

from datetime import date
from decimal import Decimal

import config
# The supplier rule lives with the keyword rules it is based on.
from tools.categorizer_tools import is_supplier_row  # noqa: F401  (re-exported for the Manager's checks)


def in_report_month(date_text):
    """True if a YYYY-MM-DD date lies in config.REPORT_MONTH."""
    return date_text[:7] == config.REPORT_MONTH


def days_between(date_a, date_b):
    return abs((date.fromisoformat(date_a) - date.fromisoformat(date_b)).days)


def same_charge(row_a, row_b):
    """Possible duplicate: same counterparty and amount, at most
    config.DUPLICATE_WINDOW_DAYS days apart - whatever the wording."""
    return (row_a["counterparty"].strip().casefold() == row_b["counterparty"].strip().casefold()
            and Decimal(row_a["amount_czk"]) == Decimal(row_b["amount_czk"])
            and days_between(row_a["date"], row_b["date"]) <= config.DUPLICATE_WINDOW_DAYS)


def possible_duplicate_pairs(rows):
    """All (later_row, earlier_row) pairs that look like the same charge.
    Rows are compared in file order (source_line)."""
    ordered = sorted(rows, key=lambda row: int(row["source_line"]))
    pairs = []
    for index, row in enumerate(ordered):
        for earlier in ordered[:index]:
            if same_charge(row, earlier):
                pairs.append((row, earlier))
                break
    return pairs
