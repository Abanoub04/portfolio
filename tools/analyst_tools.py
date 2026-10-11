"""The Analyst's tools: every number in the report is calculated here.

The Analyst (the AI) only decides which calculation to run. Python does
the arithmetic, with Decimal so money is exact to the haléř.

Sign convention in the analysis: expenses are shown as positive spend
amounts (like a budget report), sales income as a positive amount.
Variance = actual - budget, so a positive variance means OVER budget.

The result is saved as one file (output/analysis_YYYY-MM.json). It is the
Writer's only source of numbers. Every amount in it is already formatted
for the report (e.g. "42,000" and "+68.0%"), so the Writer only copies.
"""

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import config
from tools.categorizer_tools import keyword_matches
from tools.csv_helpers import read_csv


def format_czk(amount):
    """42000 -> "42,000"; 1289.5 -> "1,289.50" (decimals only when needed)."""
    if amount == amount.to_integral_value():
        return f"{amount:,.0f}"
    return f"{amount:,.2f}"


def format_signed_czk(amount):
    """Variance in CZK with a sign: +17,000 or -5,370."""
    sign = "+" if amount > 0 else "-" if amount < 0 else ""
    return sign + format_czk(abs(amount))


def display_amount(amount):
    """How an amount is shown in the exception lists: money going out as a
    plain amount (1,840), money coming in with a plus sign (+3,100)."""
    if amount > 0:
        return "+" + format_czk(amount)
    return format_czk(-amount)


def variance_phrase(variance, percent):
    """Variance in plain words, without + or - signs."""
    if variance == 0:
        return "on budget"
    direction = "over budget" if variance > 0 else "under budget"
    if percent is None:
        return f"CZK {format_czk(abs(variance))} {direction} (no budget set)"
    return f"CZK {format_czk(abs(variance))} ({abs(percent)}%) {direction}"


def format_percent(value):
    """Variance in % with one decimal and a sign: +68.0%. None -> "n/a"."""
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value}%"


class ReportAnalyst:
    """Holds the month's data in memory while the Analyst works."""

    def __init__(self, output_dir=None, budget_file=None):
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        self.budget_file = Path(budget_file or config.BUDGET_FILE)
        self.transactions = []
        self.exceptions = []
        self.budget = {}
        # The results of each calculation, filled in by the tools below.
        self.results = {}

    def require_loaded(self):
        if not self.transactions:
            raise RuntimeError("No data loaded - call load_month_data first")

    def expense_categories(self):
        """All categories except Sales, in the order from config.py."""
        return [category for category in config.CATEGORIES if category != "Sales"]

    def actual_spend(self, category):
        """Spend in one category as a positive amount."""
        total = Decimal(0)
        for row in self.transactions:
            if row["category"] == category:
                total += Decimal(row["amount_czk"])
        return -total if category != "Sales" else total

    # --- tools ------------------------------------------------------------

    def load_month_data(self):
        """Read the categorized transactions, the budget and the exceptions."""
        categorized_path = self.output_dir / config.CATEGORIZED_FILE_NAME
        if not categorized_path.exists():
            raise FileNotFoundError(f"{categorized_path.name} not found - the Bookkeeping department must run first")

        self.transactions = read_csv(categorized_path)
        self.exceptions = read_csv(self.output_dir / config.EXCEPTIONS_FILE_NAME)
        self.budget = {}
        for row in read_csv(self.budget_file):
            self.budget[row["category"]] = Decimal(row["budget_czk"])
        self.results = {}

        return {
            "transactions": len(self.transactions),
            "exceptions": len(self.exceptions),
            "budget_categories": list(self.budget),
        }

    def calculate_totals(self):
        """Total spend per category, total expenses and sales income."""
        self.require_loaded()

        categories = []
        total_expenses = Decimal(0)
        for category in self.expense_categories():
            spend = self.actual_spend(category)
            count = sum(1 for row in self.transactions if row["category"] == category)
            total_expenses += spend
            categories.append({"category": category, "transactions": count, "actual_czk": format_czk(spend)})

        sales = self.actual_spend("Sales")
        sales_count = sum(1 for row in self.transactions if row["category"] == "Sales")

        # Refunds: positive amounts in an expense category. They are already
        # netted in the category's actual; listed so the report can say how
        # much of a category's variance a refund explains.
        refunds = {}
        for row in self.transactions:
            amount = Decimal(row["amount_czk"])
            if row["category"] != "Sales" and amount > 0:
                item = refunds.setdefault(row["category"], {"total": Decimal(0), "lines": []})
                item["total"] += amount
                item["lines"].append(int(row["source_line"]))
        refunds = {category: {"total_czk": format_czk(item["total"]), "lines": item["lines"]}
                   for category, item in refunds.items()}

        self.results["totals"] = {
            "categories": categories,
            "total_expenses_czk": format_czk(total_expenses),
            "expense_transactions": len(self.transactions) - sales_count,
            "sales_income_czk": format_czk(sales),
            "sales_transactions": sales_count,
            "refunds": refunds,
        }
        return self.results["totals"]

    def compare_to_budget(self):
        """Budget vs actual per expense category: variance in CZK and %."""
        self.require_loaded()

        rows = []
        total_actual = Decimal(0)
        total_budget = Decimal(0)
        for category in self.expense_categories():
            actual = self.actual_spend(category)
            budget = self.budget.get(category, Decimal(0))
            total_actual += actual
            total_budget += budget
            rows.append(self.variance_row(category, actual, budget))

        self.results["budget_vs_actual"] = {
            "categories": rows,
            "total": self.variance_row("Total expenses", total_actual, total_budget),
            "note": "Variance = actual - budget; + means over budget",
        }
        return self.results["budget_vs_actual"]

    def variance_row(self, name, actual, budget):
        variance = actual - budget
        if budget == 0:
            percent = None
        else:
            percent = (variance / budget * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return {
            "category": name,
            "actual_czk": format_czk(actual),
            "budget_czk": format_czk(budget),
            "variance_czk": format_signed_czk(variance),
            "variance_percent": format_percent(percent),
            # The same variance in words, without signs, for sentences:
            # "CZK 33,514 (5.5%) under budget" - never "CZK -33,514 under budget".
            "variance_phrase": variance_phrase(variance, percent),
            "variance_direction": ("over budget" if variance > 0 else "under budget" if variance < 0
                                   else "on budget"),
            # Kept unformatted too, so find_unusual_items can compare it.
            "_percent_value": None if percent is None else str(percent),
        }

    def find_unusual_items(self):
        """Categories more than the threshold over or under budget, spend with
        no budget, and single expenses above the large-transaction threshold
        (outside the excluded categories)."""
        self.require_loaded()
        if "budget_vs_actual" not in self.results:
            self.compare_to_budget()

        threshold_percent = Decimal(str(config.OVER_BUDGET_THRESHOLD * 100))
        over_budget = []
        under_budget = []
        for row in self.results["budget_vs_actual"]["categories"]:
            if row["_percent_value"] is None:
                if row["actual_czk"] != "0":
                    over_budget.append({**self.public(row), "why": "spend with no budget"})
                continue
            percent = Decimal(row["_percent_value"])
            if percent > threshold_percent:
                over_budget.append({**self.public(row), "why": f"more than {threshold_percent:.0f}% over budget"})
            elif percent < -threshold_percent:
                # Spending far below budget is not automatically good news:
                # costs may be missing or booked late.
                under_budget.append({**self.public(row), "why": f"more than {threshold_percent:.0f}% under budget",
                                     "note": "may indicate missing or late costs"})

        # For each flagged category, its 3 largest expenses, so the report
        # can explain what drove the overspend.
        for item in over_budget:
            rows = [row for row in self.transactions if row["category"] == item["category"]]
            rows.sort(key=lambda row: Decimal(row["amount_czk"]))  # most negative = largest spend first
            item["largest_items"] = [
                {"source_line": int(row["source_line"]), "description": row["description"],
                 "amount_czk": format_czk(-Decimal(row["amount_czk"]))}
                for row in rows[:3]
            ]

        large = []
        limit = Decimal(config.LARGE_TRANSACTION_THRESHOLD)
        for row in self.transactions:
            if row["category"] == "Sales" or row["category"] in config.LARGE_TRANSACTION_EXCLUDED_CATEGORIES:
                continue
            spend = -Decimal(row["amount_czk"])
            if spend > limit:
                large.append({
                    "source_line": int(row["source_line"]),
                    "date": row["date"],
                    "description": row["description"],
                    "category": row["category"],
                    "amount_czk": format_czk(spend),
                })

        self.results["unusual_items"] = {
            "over_budget_threshold": f"{threshold_percent:.0f}%",
            "categories_over_budget": over_budget,
            "categories_under_budget": under_budget,
            "large_transaction_threshold_czk": format_czk(limit),
            "large_transactions_excluding": config.LARGE_TRANSACTION_EXCLUDED_CATEGORIES,
            "large_transactions": large,
        }
        return self.results["unusual_items"]

    def public(self, row):
        """A copy of a row without the internal fields (those starting with _)."""
        return {key: value for key, value in row.items() if not key.startswith("_")}

    def summarize_exceptions(self):
        """Every row set aside by the Collector (duplicates, rows outside the
        period, missing amounts, other issues) and every row needing review."""
        self.require_loaded()

        groups = {"probable duplicate": [], "possible duplicate": [], "outside the period": []}
        totals = {issue: Decimal(0) for issue in groups}
        missing = []
        other_issues = []
        for row in self.exceptions:
            line = int(row["source_line"])
            if row["issue"] in groups:
                amount = Decimal(row["amount_czk"]) if row["amount_czk"] else Decimal(0)
                totals[row["issue"]] += -amount
                groups[row["issue"]].append({"source_line": line, "date": row["date"],
                                             "description": row["description"],
                                             "amount_czk": display_amount(amount), "detail": row["detail"]})
            elif row["issue"] == "missing amount":
                # Which category the row would most likely fall into, using the
                # Categorizer's keyword rules. Its actual is understated until
                # the amount is known.
                matches = keyword_matches(row["description"])
                likely = matches[0] if len(matches) == 1 else "unclear"
                missing.append({"source_line": line, "date": row["date"],
                                "description": row["description"], "counterparty": row["counterparty"],
                                "likely_category": likely})
            else:
                other_issues.append({"source_line": line, "issue": row["issue"], "detail": row["detail"]})

        needs_review = []
        for row in self.transactions:
            if row.get("needs_review") == "yes":
                amount = Decimal(row["amount_czk"])
                refund = row["category"] != "Sales" and amount > 0
                needs_review.append({"source_line": int(row["source_line"]), "date": row["date"],
                                     "description": row["description"],
                                     "category": row["category"] + (" (refund)" if refund else ""),
                                     "amount_czk": display_amount(amount),
                                     "review_reason": row["review_reason"]})

        # Category -> lines with a missing amount (its actual is understated).
        understated = {}
        for item in missing:
            if item["likely_category"] != "unclear":
                understated.setdefault(item["likely_category"], []).append(item["source_line"])

        self.results["exceptions"] = {
            "probable_duplicates": groups["probable duplicate"],
            "probable_duplicates_count": len(groups["probable duplicate"]),
            "probable_duplicates_total_czk": format_czk(totals["probable duplicate"]),
            "possible_duplicates": groups["possible duplicate"],
            "possible_duplicates_count": len(groups["possible duplicate"]),
            "possible_duplicates_total_czk": format_czk(totals["possible duplicate"]),
            "duplicate_window_days": config.DUPLICATE_WINDOW_DAYS,
            "outside_the_period": groups["outside the period"],
            "outside_the_period_count": len(groups["outside the period"]),
            "missing_amounts": missing,
            "missing_amounts_count": len(missing),
            "understated_categories": understated,
            "other_issues": other_issues,
            "needs_review": needs_review,
            "needs_review_count": len(needs_review),
        }
        return self.results["exceptions"]

    def save_analysis(self):
        """Save all results for the Writer. Only works when every part is done."""
        needed = ["totals", "budget_vs_actual", "unusual_items", "exceptions"]
        missing = [part for part in needed if part not in self.results]
        if missing:
            raise RuntimeError(f"Not finished yet - still missing: {missing}")

        # Drop the internal fields before saving.
        budget = self.results["budget_vs_actual"]
        analysis = {
            "report_month": config.REPORT_MONTH,
            "currency": config.CURRENCY,
            "totals": self.results["totals"],
            "budget_vs_actual": {
                "categories": [self.public(row) for row in budget["categories"]],
                "total": self.public(budget["total"]),
                "note": budget["note"],
            },
            "unusual_items": self.results["unusual_items"],
            "exceptions": self.results["exceptions"],
        }

        path = self.output_dir / config.ANALYSIS_FILE_NAME
        path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"file": path.name, "sections": list(analysis)}


def make_analyst_tools(analyst):
    """The Analyst's tool list."""
    no_inputs = {"type": "object", "properties": {}}
    return [
        {
            "name": "load_month_data",
            "description": "Load the categorized transactions, the budget and the exceptions list.",
            "input_schema": no_inputs,
            "function": analyst.load_month_data,
        },
        {
            "name": "calculate_totals",
            "description": "Calculate total spend per expense category, total expenses and sales income.",
            "input_schema": no_inputs,
            "function": analyst.calculate_totals,
        },
        {
            "name": "compare_to_budget",
            "description": "Compare actual spend with budget per category: variance in CZK and %.",
            "input_schema": no_inputs,
            "function": analyst.compare_to_budget,
        },
        {
            "name": "find_unusual_items",
            "description": f"Find categories more than {config.OVER_BUDGET_THRESHOLD:.0%} over or under budget and single "
                           f"expenses above {config.LARGE_TRANSACTION_THRESHOLD:,} CZK outside "
                           f"{' and '.join(config.LARGE_TRANSACTION_EXCLUDED_CATEGORIES)}.",
            "input_schema": no_inputs,
            "function": analyst.find_unusual_items,
        },
        {
            "name": "summarize_exceptions",
            "description": "Summarize every row set aside (probable and possible duplicates, rows outside "
                           "the period, missing amounts) and every row needing review.",
            "input_schema": no_inputs,
            "function": analyst.summarize_exceptions,
        },
        {
            "name": "save_analysis",
            "description": "Save all results for the Writer. Call this last.",
            "input_schema": no_inputs,
            "function": analyst.save_analysis,
        },
    ]
