"""Tests for the Reporting department (Stage 4) and the Categorizer's
needs_review flag.

The main test runs all four agents in test mode and checks every number in
the finished report against the answer key, read directly from
data/README.md. Run from the project root with:   python -m unittest -v
"""

import json
import os
import re
import tempfile
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from unittest import mock

import config
from agents.action_log import ActionLog
from agents.analyst import create_analyst
from agents.categorizer import create_categorizer
from agents.collector import create_collector
from agents.writer import create_writer
from tools.analyst_tools import ReportAnalyst
from tools.categorizer_tools import TransactionCategorizer
from tools.collector_tools import TransactionCleaner
from tools.csv_helpers import write_csv
from tools.writer_tools import ReportWriter, numbers_in


def read_answer_key():
    """Read the answer-key table from data/README.md.
    Returns {name: {"actual": Decimal, "budget": Decimal or None, "percent": int or None}}."""
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


def report_table_rows(report):
    """The rows of the budget vs actual table in the report, by category."""
    section = report.split("## Budget vs actual", 1)[1].split("##", 1)[0]
    rows = {}
    for line in section.splitlines():
        if not line.startswith("|") or "---" in line or "Category" in line:
            continue
        cells = [cell.replace("*", "").strip() for cell in line.strip("|").split("|")]
        rows[cells[0]] = cells[1:]
    return rows


def as_decimal(text):
    return Decimal(text.replace(",", "").replace("%", "").replace("+", ""))


@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
class FullReportTests(unittest.TestCase):
    """Runs all four agents once, then checks the report from every angle."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temp_dir.name)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            log = ActionLog(cls.output_dir / "logs")
            create_collector(log, output_dir=cls.output_dir).run("Clean.")
            create_categorizer(log, output_dir=cls.output_dir).run("Categorize.")
            create_analyst(log, output_dir=cls.output_dir).run("Analyse.")
            create_writer(log, output_dir=cls.output_dir).run("Write.")
        cls.log_text = log.path.read_text(encoding="utf-8")
        cls.report = (cls.output_dir / config.DRAFT_REPORT_FILE_NAME).read_text(encoding="utf-8")
        cls.analysis = json.loads((cls.output_dir / config.ANALYSIS_FILE_NAME).read_text(encoding="utf-8"))
        cls.key = read_answer_key()
        cls.table = report_table_rows(cls.report)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_answer_key_was_read(self):
        self.assertEqual(len(self.key), 9)   # 7 categories + total + sales

    def test_category_rows_match_answer_key(self):
        for category in ["Salaries", "Rent", "Travel", "Software", "Marketing", "Utilities", "Other"]:
            with self.subTest(category=category):
                actual, budget, variance, percent = self.table[category]
                expected = self.key[category]
                self.assertEqual(as_decimal(actual), expected["actual"])
                self.assertEqual(as_decimal(budget), expected["budget"])
                self.assertEqual(as_decimal(variance), expected["actual"] - expected["budget"])
                # The answer key shows % rounded to whole numbers; the report to 0.1.
                rounded = as_decimal(percent).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                self.assertEqual(rounded, expected["percent"])

    def test_total_row_matches_answer_key(self):
        actual, budget, variance, percent = self.table["Total expenses"]
        expected = self.key["Total expenses"]
        self.assertEqual(as_decimal(actual), expected["actual"])
        self.assertEqual(as_decimal(budget), expected["budget"])
        self.assertEqual(as_decimal(variance), expected["actual"] - expected["budget"])
        self.assertEqual(as_decimal(percent).quantize(Decimal("1"), rounding=ROUND_HALF_UP), expected["percent"])

    def test_sales_income_matches_answer_key(self):
        sales = self.key["Sales (income)"]["actual"]
        self.assertIn(f"Side note: sales income for the month was {sales:,}", self.report)

    def test_flagged_categories_are_travel_and_marketing(self):
        # Answer key: Travel +70 % and Marketing +68 % are flagged; Other +16 % is below 20 %.
        flagged = [item["category"] for item in self.analysis["unusual_items"]["categories_over_budget"]]
        self.assertEqual(flagged, ["Travel", "Marketing"])
        self.assertEqual(self.analysis["unusual_items"]["large_transactions"], [])
        self.assertIn("- **Travel**: actual 25,546 vs budget 15,000 (+10,546, +70.3%)", self.report)
        self.assertIn("- **Marketing**: actual 42,000 vs budget 25,000 (+17,000, +68.0%)", self.report)

    def test_exceptions_match_answer_key(self):
        exceptions = self.report.split("## Exceptions", 1)[1]
        duplicates = exceptions.split("**Missing amounts", 1)[0]
        missing = exceptions.split("**Missing amounts", 1)[1].split("**Items needing review", 1)[0]
        review = exceptions.split("**Items needing review", 1)[1]

        self.assertEqual(re.findall(r"^\| (\d+) \|", duplicates, re.M), ["16", "19", "22", "39"])
        self.assertIn("(4, total 26,440)", duplicates)        # 1,840 + 3,400 + 12,000 + 9,200
        self.assertEqual(re.findall(r"^\| (\d+) \|", missing, re.M), ["8", "33", "41"])
        self.assertEqual(re.findall(r"^\| (\d+) \|", review, re.M), ["47"])

    def test_every_number_in_report_comes_from_the_analysis(self):
        allowed = set(numbers_in(json.dumps(self.analysis, ensure_ascii=False)))
        invented = [n for n in numbers_in(self.report) if n not in allowed]
        self.assertEqual(invented, [])

    def test_summary_numbers_match_answer_key(self):
        summary = self.report.split("## Summary", 1)[1].split("##", 1)[0]
        total = self.key["Total expenses"]
        self.assertIn(f"{total['actual']:,} CZK against a budget of {total['budget']:,} CZK", summary)
        self.assertIn(f"Side note: sales income was {self.key['Sales (income)']['actual']:,} CZK", summary)

    def test_no_result_line(self):
        # Sales minus expenses is not shown; sales appear only as a side note.
        self.assertNotIn("result", self.report.lower())
        self.assertNotIn("result_czk", json.dumps(self.analysis))

    def test_under_budget_categories_are_flagged(self):
        # Software is -29.8% against budget (answer key -30 %): more than 20% under.
        under = self.analysis["unusual_items"]["categories_under_budget"]
        self.assertEqual([item["category"] for item in under], ["Software"])
        self.assertIn("- **Software**: actual 12,630 vs budget 18,000 (-5,370, -29.8%). "
                      "Note: may indicate missing or late costs.", self.report)

    def test_missing_amounts_show_likely_category(self):
        likely = {item["source_line"]: item["likely_category"]
                  for item in self.analysis["exceptions"]["missing_amounts"]}
        self.assertEqual(likely, {8: "Software", 33: "Other", 41: "Travel"})
        self.assertIn("| 8 | 2026-09-03 | Figma Professional | Figma Inc. | Software |", self.report)
        self.assertIn("| 41 | 2026-09-19 | Taxi Berlin airport | Berlin Taxi | Travel |", self.report)
        # The understated categories are marked in the budget table, with a footnote.
        self.assertIn("| Software * | 12,630 |", self.report)
        self.assertIn("Actual understated – amount still missing for: Software (line 8); "
                      "Other (line 33); Travel (line 41)", self.report)

    def test_invented_number_was_rejected_and_logged(self):
        self.assertIn("Report NOT saved", self.log_text)
        self.assertIn("623,000", self.log_text)
        self.assertNotIn("623,000", self.report)


class WriterNumberCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.writer = ReportWriter(output_dir=self.temp_dir.name)
        self.writer.analysis = {"report_month": "2026-09", "total": "622,894", "percent": "+3.0%"}

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_copied_numbers_pass(self):
        self.assertEqual(self.writer.unknown_numbers("Expenses were 622,894 CZK (+3.0%) in September 2026."), [])

    def test_rounded_or_calculated_numbers_fail(self):
        self.assertEqual(self.writer.unknown_numbers("About 623,000 CZK, 3.1% over."), ["623,000", "3.1"])


class AnalystToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        rows = [
            {"source_line": 2, "date": "2026-09-01", "description": "New laptops", "counterparty": "X",
             "amount_czk": "-25000.00", "category": "Software", "needs_review": "no"},
            {"source_line": 3, "date": "2026-09-30", "description": "Salary", "counterparty": "Y",
             "amount_czk": "-90000.00", "category": "Salaries", "needs_review": "no"},
            {"source_line": 4, "date": "2026-09-10", "description": "Invoice", "counterparty": "Z",
             "amount_czk": "50000.00", "category": "Sales", "needs_review": "no"},
        ]
        columns = ["source_line", "date", "description", "counterparty", "amount_czk", "category", "needs_review"]
        write_csv(self.output_dir / config.CATEGORIZED_FILE_NAME, rows, columns)
        write_csv(self.output_dir / config.EXCEPTIONS_FILE_NAME, [], ["source_line", "issue"])
        budget = self.output_dir / "budget.csv"
        write_csv(budget, [{"category": "Software", "budget_czk": "20000"},
                           {"category": "Salaries", "budget_czk": "100000"}], ["category", "budget_czk"])
        self.analyst = ReportAnalyst(output_dir=self.output_dir, budget_file=budget)
        self.analyst.load_month_data()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_variance_in_czk_and_percent(self):
        rows = {row["category"]: row for row in self.analyst.compare_to_budget()["categories"]}
        self.assertEqual(rows["Software"]["variance_czk"], "+5,000")
        self.assertEqual(rows["Software"]["variance_percent"], "+25.0%")
        self.assertEqual(rows["Salaries"]["variance_czk"], "-10,000")
        self.assertEqual(rows["Salaries"]["variance_percent"], "-10.0%")
        self.assertEqual(rows["Travel"]["variance_percent"], "n/a")   # no budget, no spend

    def test_large_transactions_skip_salaries_rent_and_sales(self):
        unusual = self.analyst.find_unusual_items()
        self.assertEqual([x["source_line"] for x in unusual["large_transactions"]], [2])
        self.assertEqual([x["category"] for x in unusual["categories_over_budget"]], ["Software"])

    def test_cannot_save_unfinished_analysis(self):
        self.analyst.calculate_totals()
        with self.assertRaises(RuntimeError):
            self.analyst.save_analysis()


class NeedsReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        cleaner = TransactionCleaner(output_dir=self.temp_dir.name)
        for step in [cleaner.load_transactions, cleaner.standardize_dates,
                     cleaner.flag_missing_amounts, cleaner.remove_duplicates, cleaner.save_cleaned_data]:
            step()
        self.categorizer = TransactionCategorizer(output_dir=self.temp_dir.name)
        self.categorizer.load_cleaned_data()
        self.categorizer.apply_keyword_rules()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_review_flag_needs_a_reason(self):
        with self.assertRaises(ValueError):
            self.categorizer.set_category(47, "Other", "Transfer", needs_review=True, review_reason=" ")

    def test_review_flag_is_saved_with_one_category(self):
        self.categorizer.set_category(29, "Other", "Supermarket")
        self.categorizer.set_category(43, "Other", "Electronics")
        result = self.categorizer.set_category(47, "Other", "Transfer", needs_review=True,
                                               review_reason="Confirm purpose")
        self.assertEqual(result["needs_review"], "yes")
        saved = self.categorizer.save_categorized_data()
        self.assertEqual(saved["needs_review"], [47])


if __name__ == "__main__":
    unittest.main()
