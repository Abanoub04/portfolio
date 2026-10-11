"""The answer key for the fake September 2026 data.

The totals table is read straight from data/README.md, so there is one
source of truth. The row-level facts (which lines are duplicates, missing
or unclear) are the planted mess described in the same README.
"""

import re
from decimal import Decimal

import config

RAW_ROWS = 61
ROWS_AFTER_DUPLICATES = 57
CLEAN_ROWS = 54
DUPLICATE_LINES = {16: 15, 19: 18, 22: 21, 39: 38}   # duplicate line -> original line
MISSING_AMOUNT_LINES = {8, 33, 41}                   # Figma, Courier, Taxi Berlin airport
# The rows the keyword rules can't decide. The answer key counts them as Other.
UNCLEAR_LINES = {29: "Other", 43: "Other", 47: "Other"}   # ALBERT, ALZA, Transfer
# With the answer-key categories, these are flagged (more than 20% over/under budget).
OVER_BUDGET = ["Travel", "Marketing"]
UNDER_BUDGET = ["Software"]


def read_totals_table():
    """The answer-key table from data/README.md:
    {name: {"actual": Decimal, "budget": Decimal or None, "percent": Decimal or None}}."""
    text = (config.DATA_DIR / "README.md").read_text(encoding="utf-8")
    key_section = text.split("## Answer key", 1)[1]

    def number(cell):
        cell = cell.replace("*", "").replace(" ", "").replace("−", "-").replace("%", "")
        match = re.match(r"^[+-]?\d+", cell)
        return Decimal(match.group()) if match else None

    key = {}
    for line in key_section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("Category", "---") or set(cells[0]) <= set("-"):
            continue
        name = cells[0].replace("*", "").strip()
        key[name] = {"actual": number(cells[1]), "budget": number(cells[2]), "percent": number(cells[3])}
    return key
