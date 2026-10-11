"""The answer keys for the fake test months.

Each month's totals table is read straight from its markdown file in data/,
so there is one source of truth. The row-level facts (which lines are
duplicates, missing, outside the period or unclear) are the planted
problems described in the same file.

A month without an answer key (e.g. real data) simply has none: the run
check then skips the comparisons with the key.
"""

import re
from decimal import Decimal

import config

ANSWER_KEYS = {
    "2026-09": {
        "file": "README.md",
        "raw_rows": 61,
        "clean_rows": 54,
        "probable_duplicates": {16: 15, 19: 18, 22: 21, 39: 38},   # duplicate line -> original line
        "missing_amounts": {8, 33, 41},                            # Figma, Courier, Taxi Berlin airport
        "outside_period": set(),
        # Rows the keyword rules can't decide, with the answer-key category.
        "unclear_lines": {29: "Other", 43: "Other", 47: "Other"},  # ALBERT, ALZA, Transfer
        "over_budget": ["Travel", "Marketing"],
        "under_budget": ["Software"],
    },
    "2026-10": {
        "file": "answer_key_2026-10.md",
        "raw_rows": 47,
        "clean_rows": 45,
        "probable_duplicates": {6: 5},          # Adobe, same charge with different wording
        "missing_amounts": set(),
        "outside_period": {32},                 # printer toner dated 28.09.2026
        "unclear_lines": {16: "Software",       # Taskly - new supplier, no keyword rule
                          25: "Travel"},        # Refund - Hotel Berlin (reduces Travel)
        "over_budget": [],
        "under_budget": ["Travel", "Marketing", "Other"],
    },
}


def for_month(month=None):
    """The answer key of a month (default: the current month), or None."""
    return ANSWER_KEYS.get(month or config.REPORT_MONTH)


def read_totals_table(month=None):
    """The answer-key totals table from the month's markdown file:
    {name: {"actual": Decimal, "budget": Decimal or None, "percent": Decimal or None}}."""
    key = for_month(month)
    text = (config.DATA_DIR / key["file"]).read_text(encoding="utf-8")
    key_section = text.split("## Answer key", 1)[1]

    def number(cell):
        cell = cell.replace("*", "").replace(" ", "").replace("−", "-").replace("%", "")
        match = re.match(r"^[+-]?\d+", cell)
        return Decimal(match.group()) if match else None

    table = {}
    for line in key_section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("Category", "---") or set(cells[0]) <= set("-"):
            continue
        name = cells[0].replace("*", "").strip()
        table[name] = {"actual": number(cells[1]), "budget": number(cells[2]), "percent": number(cells[3])}
    return table
