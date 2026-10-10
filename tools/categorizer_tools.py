"""The Categorizer's tools: give every clean transaction exactly one category.

How it works:
  1. apply_keyword_rules() handles the obvious rows with a fixed keyword
     list (e.g. "salary" -> Salaries). This is the firm's policy, written
     in Python, so it gives the same answer every time.
  2. Rows the keywords can't decide are left for the AI. It looks at each
     one and calls set_category() with a category and a short reason.
  3. save_categorized_data() refuses to save until every row has exactly
     one category from the allowed list.

Sign rule (checked for keywords and AI alike): Sales must be money coming
in (positive amount); every other category is money going out (negative).
"""

import re
from decimal import Decimal
from pathlib import Path

import config
from tools.csv_helpers import read_csv, write_csv

CATEGORIZED_COLUMNS = ["source_line", "date", "description", "counterparty", "amount_czk",
                       "category", "method", "reason"]

# Keyword rules: a row gets a category when its description contains one of
# these words or phrases (as whole words, case doesn't matter).
KEYWORD_RULES = {
    "Salaries": ["salary", "social security", "health insurance"],
    "Rent": ["rent", "service charges"],
    "Utilities": ["electricity", "internet", "mobile"],
    "Software": ["adobe", "microsoft 365", "figma", "software", "hosting", "domain",
                 "slack", "password manager", "cloud backup"],
    "Travel": ["train", "hotel", "taxi", "fuel", "flight", "airport"],
    "Marketing": ["google ads", "linkedin ads", "brochures", "stock photos", "conference booth"],
    "Sales": ["invoice"],
    "Other": ["office supplies", "coffee", "cleaning", "bank fees", "postage", "courier",
              "water cooler", "accountant"],
}


def keyword_matches(description):
    """Return the list of categories whose keywords appear in the description."""
    text = description.lower()
    matches = []
    for category, keywords in KEYWORD_RULES.items():
        for keyword in keywords:
            # \b means "word boundary", so "rent" matches "Office rent"
            # but not "Water cooler rental".
            if re.search(r"\b" + re.escape(keyword) + r"\b", text):
                matches.append(category)
                break
    return matches


def sign_problem(category, amount_text):
    """Return an error message if the amount's sign doesn't fit the category."""
    amount = Decimal(amount_text)
    if category == "Sales" and amount <= 0:
        return "Sales must be a positive amount (money coming in)"
    if category != "Sales" and amount > 0:
        return f"{category} is an expense, but the amount is positive (money coming in)"
    return None


class TransactionCategorizer:
    """Holds the clean transactions in memory while the Categorizer works."""

    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        self.rows = []

    def find_row(self, source_line):
        for row in self.rows:
            if int(row["source_line"]) == int(source_line):
                return row
        return None

    def short_view(self, row):
        """The fields the AI needs to judge a row."""
        return {
            "source_line": int(row["source_line"]),
            "description": row["description"],
            "counterparty": row["counterparty"],
            "amount_czk": row["amount_czk"],
        }

    # --- tools ------------------------------------------------------------

    def load_cleaned_data(self):
        """Read the Collector's clean file."""
        path = self.output_dir / config.CLEAN_FILE_NAME
        if not path.exists():
            raise FileNotFoundError(f"{path.name} not found - the Collector must run first")

        self.rows = read_csv(path)
        for row in self.rows:
            row["category"] = ""
            row["method"] = ""
            row["reason"] = ""
        return {"file": path.name, "rows_loaded": len(self.rows)}

    def apply_keyword_rules(self):
        """Categorize the obvious rows. Rows matching no keyword, several
        categories, or the wrong sign are left for the AI."""
        if not self.rows:
            raise RuntimeError("No data loaded - call load_cleaned_data first")

        categorized = {}
        left_for_ai = []
        for row in self.rows:
            if row["category"]:
                continue  # already decided

            matches = keyword_matches(row["description"])
            if len(matches) == 1 and not sign_problem(matches[0], row["amount_czk"]):
                category = matches[0]
                row["category"] = category
                row["method"] = "keyword"
                row["reason"] = "Matched keyword rule"
                categorized[category] = categorized.get(category, 0) + 1
                continue

            # Explain to the AI why the keywords could not decide.
            view = self.short_view(row)
            if not matches:
                view["why_unclear"] = "no keyword matched"
            elif len(matches) > 1:
                view["why_unclear"] = f"keywords for several categories matched: {matches}"
            else:
                view["why_unclear"] = f"keyword says {matches[0]}, but {sign_problem(matches[0], row['amount_czk'])}"
            left_for_ai.append(view)

        return {
            "categorized_by_keyword": sum(categorized.values()),
            "by_category": categorized,
            "left_for_you_to_decide": left_for_ai,
        }

    def list_uncategorized(self):
        """Show the rows that still have no category."""
        return [self.short_view(row) for row in self.rows if not row["category"]]

    def set_category(self, source_line, category, reason):
        """Give one uncategorized row its category (decided by the AI)."""
        if category not in config.CATEGORIES:
            raise ValueError(f"'{category}' is not allowed. Use one of: {', '.join(config.CATEGORIES)}")

        row = self.find_row(source_line)
        if row is None:
            raise ValueError(f"No clean transaction on source line {source_line}")
        if row["category"]:
            raise ValueError(f"Line {source_line} already has category {row['category']} "
                             f"({row['method']}); each transaction gets exactly one category")

        problem = sign_problem(category, row["amount_czk"])
        if problem:
            raise ValueError(f"Line {source_line}: {problem}")

        row["category"] = category
        row["method"] = "AI"
        row["reason"] = reason.strip() or "(no reason given)"
        return {"source_line": int(source_line), "category": category, "still_uncategorized": len(self.list_uncategorized())}

    def save_categorized_data(self):
        """Save the categorized file. Refuses while any row has no category."""
        missing = self.list_uncategorized()
        if missing:
            lines = [row["source_line"] for row in missing]
            raise RuntimeError(f"{len(missing)} rows still have no category (lines {lines}). "
                               f"Every transaction needs exactly one category.")

        path = self.output_dir / config.CATEGORIZED_FILE_NAME
        write_csv(path, self.rows, CATEGORIZED_COLUMNS)

        per_category = {category: 0 for category in config.CATEGORIES}
        by_method = {}
        for row in self.rows:
            per_category[row["category"]] += 1
            by_method[row["method"]] = by_method.get(row["method"], 0) + 1

        return {
            "file": path.name,
            "rows_saved": len(self.rows),
            "transactions_per_category": per_category,
            "categorized_by": by_method,
        }


def make_categorizer_tools(categorizer):
    """The Categorizer's tool list."""
    no_inputs = {"type": "object", "properties": {}}
    return [
        {
            "name": "load_cleaned_data",
            "description": "Load the clean transactions produced by the Collector.",
            "input_schema": no_inputs,
            "function": categorizer.load_cleaned_data,
        },
        {
            "name": "apply_keyword_rules",
            "description": "Categorize the obvious transactions with the firm's keyword rules. "
                           "Returns the rows the rules could not decide, with the reason.",
            "input_schema": no_inputs,
            "function": categorizer.apply_keyword_rules,
        },
        {
            "name": "list_uncategorized",
            "description": "List the transactions that still have no category.",
            "input_schema": no_inputs,
            "function": categorizer.list_uncategorized,
        },
        {
            "name": "set_category",
            "description": "Give one uncategorized transaction its category, with a short reason "
                           "a controller would accept. Only for rows the keyword rules left open.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "source_line": {"type": "integer", "description": "The row's source_line"},
                    "category": {"type": "string", "enum": config.CATEGORIES},
                    "reason": {"type": "string", "description": "One sentence: why this category"},
                },
                "required": ["source_line", "category", "reason"],
            },
            "function": categorizer.set_category,
        },
        {
            "name": "save_categorized_data",
            "description": "Save the categorized transactions. Only works when every transaction "
                           "has exactly one category. Call this last.",
            "input_schema": no_inputs,
            "function": categorizer.save_categorized_data,
        },
    ]
