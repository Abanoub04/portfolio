"""Tests for the Bookkeeping department (Stage 3), checked against the
answer key in data/README.md.

They use the fake model and write to a temporary folder, so they need no
API key and never touch the real output/ folder.
Run from the project root with:   python -m unittest -v
"""

import os
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

import config
from agents.action_log import ActionLog
from agents.categorizer import create_categorizer
from agents.collector import create_collector
from tools.categorizer_tools import TransactionCategorizer
from tools.collector_tools import TransactionCleaner
from tools.csv_helpers import read_csv

# --- The answer key from data/README.md --------------------------------------
ROWS_IN_RAW_FILE = 61
ROWS_AFTER_DUPLICATES = 57          # incl. the 3 rows without an amount
CLEAN_ROWS = 54                     # rows with an amount, no duplicates
DUPLICATES = {16: 15, 19: 18, 22: 21, 39: 38}   # duplicate line -> original line
MISSING_AMOUNT_LINES = {8, 33, 41}  # Figma, Courier, Taxi Berlin airport
UNCLEAR_LINES = {29, 43, 47}        # ALBERT, ALZA, Transfer - P. Kratochvíl
EXPECTED_TOTALS = {                 # signed amounts in CZK, unclear rows as Other
    "Salaries": Decimal("-444216"),
    "Rent": Decimal("-67500"),
    "Marketing": Decimal("-42000"),
    "Travel": Decimal("-25546"),
    "Other": Decimal("-23132"),
    "Software": Decimal("-12630"),
    "Utilities": Decimal("-7870"),
    "Sales": Decimal("371000"),
}


class TempOutputTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def clean_everything(self, source_file=None):
        cleaner = TransactionCleaner(source_file=source_file, output_dir=self.output_dir)
        cleaner.load_transactions()
        cleaner.standardize_dates()
        cleaner.flag_missing_amounts()
        cleaner.remove_duplicates()
        return cleaner, cleaner.save_cleaned_data()


class CollectorToolTests(TempOutputTestCase):
    def test_row_counts_match_answer_key(self):
        cleaner, summary = self.clean_everything()
        self.assertEqual(summary["rows_loaded"], ROWS_IN_RAW_FILE)
        self.assertEqual(summary["clean_rows"], CLEAN_ROWS)
        self.assertEqual(summary["exceptions"], len(DUPLICATES) + len(MISSING_AMOUNT_LINES))
        self.assertEqual(CLEAN_ROWS + len(MISSING_AMOUNT_LINES), ROWS_AFTER_DUPLICATES)

    def test_duplicates_found_match_answer_key(self):
        self.clean_everything()
        exceptions = read_csv(self.output_dir / config.EXCEPTIONS_FILE_NAME)
        found = {int(row["source_line"]): row["detail"] for row in exceptions if row["issue"] == "duplicate"}
        self.assertEqual(set(found), set(DUPLICATES))
        for line, original in DUPLICATES.items():
            self.assertEqual(found[line], f"Same as line {original}")

    def test_missing_amounts_found_match_answer_key(self):
        self.clean_everything()
        exceptions = read_csv(self.output_dir / config.EXCEPTIONS_FILE_NAME)
        found = {int(row["source_line"]) for row in exceptions if row["issue"] == "missing amount"}
        self.assertEqual(found, MISSING_AMOUNT_LINES)

    def test_no_exception_line_is_in_clean_data(self):
        self.clean_everything()
        clean_lines = {int(row["source_line"]) for row in read_csv(self.output_dir / config.CLEAN_FILE_NAME)}
        self.assertFalse(clean_lines & (set(DUPLICATES) | MISSING_AMOUNT_LINES))

    def test_all_dates_are_yyyy_mm_dd_in_september(self):
        self.clean_everything()
        for row in read_csv(self.output_dir / config.CLEAN_FILE_NAME):
            self.assertRegex(row["date"], r"^2026-09-\d{2}$")

    def test_duplicates_need_standard_dates_first(self):
        cleaner = TransactionCleaner(output_dir=self.output_dir)
        cleaner.load_transactions()
        with self.assertRaises(RuntimeError):
            cleaner.remove_duplicates()

    def test_cannot_save_half_cleaned_data(self):
        cleaner = TransactionCleaner(output_dir=self.output_dir)
        cleaner.load_transactions()
        cleaner.standardize_dates()
        with self.assertRaises(RuntimeError):
            cleaner.save_cleaned_data()

    def test_unreadable_date_and_invalid_amount_become_exceptions(self):
        source = self.output_dir / "messy.csv"
        source.write_text(
            "date,description,counterparty,amount_czk\n"
            "2026-09-01,Good row,A,-100\n"
            "32.09.2026,Bad date,B,-200\n"
            "2026-09-02,Bad amount,C,twelve\n",
            encoding="utf-8",
        )
        cleaner, summary = self.clean_everything(source_file=source)
        self.assertEqual(summary["clean_rows"], 1)
        self.assertEqual(summary["exceptions_by_issue"], {"unreadable date": 1, "invalid amount": 1})


class CategorizerToolTests(TempOutputTestCase):
    def setUp(self):
        super().setUp()
        self.clean_everything()
        self.categorizer = TransactionCategorizer(output_dir=self.output_dir)
        self.categorizer.load_cleaned_data()

    def test_keywords_leave_only_the_unclear_rows(self):
        result = self.categorizer.apply_keyword_rules()
        left = {row["source_line"] for row in result["left_for_you_to_decide"]}
        self.assertEqual(left, UNCLEAR_LINES)
        self.assertEqual(result["categorized_by_keyword"], CLEAN_ROWS - len(UNCLEAR_LINES))

    def test_unknown_category_is_refused(self):
        self.categorizer.apply_keyword_rules()
        with self.assertRaises(ValueError):
            self.categorizer.set_category(29, "Groceries", "Supermarket")

    def test_second_category_is_refused(self):
        self.categorizer.apply_keyword_rules()
        with self.assertRaises(ValueError):
            self.categorizer.set_category(2, "Other", "Rent row already has a category")

    def test_wrong_sign_is_refused(self):
        self.categorizer.apply_keyword_rules()
        with self.assertRaises(ValueError):
            self.categorizer.set_category(29, "Sales", "An expense can't be Sales")

    def test_unknown_line_is_refused(self):
        self.categorizer.apply_keyword_rules()
        with self.assertRaises(ValueError):
            self.categorizer.set_category(8, "Software", "Line 8 is an exception, not clean data")

    def test_cannot_save_with_uncategorized_rows(self):
        self.categorizer.apply_keyword_rules()
        with self.assertRaises(RuntimeError):
            self.categorizer.save_categorized_data()

    def test_keyword_rule_uses_whole_words(self):
        from tools.categorizer_tools import keyword_matches
        self.assertEqual(keyword_matches("Water cooler rental"), ["Other"])   # not Rent
        self.assertEqual(keyword_matches("Office rent September"), ["Rent"])


@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
class DepartmentRunTests(TempOutputTestCase):
    """Runs both agents through the engine in test mode, like main.py does."""

    def test_full_department_run(self):
        log = ActionLog(self.output_dir / "logs")
        create_collector(log, output_dir=self.output_dir).run("Clean the file.")
        create_categorizer(log, output_dir=self.output_dir).run("Categorize.")

        rows = read_csv(self.output_dir / config.CATEGORIZED_FILE_NAME)
        self.assertEqual(len(rows), CLEAN_ROWS)

        # Every transaction has exactly one category from the allowed list.
        for row in rows:
            self.assertIn(row["category"], config.CATEGORIES)

        # The totals per category match the answer key exactly.
        totals = {}
        for row in rows:
            totals[row["category"]] = totals.get(row["category"], Decimal(0)) + Decimal(row["amount_czk"])
        self.assertEqual(totals, EXPECTED_TOTALS)

        # The log shows both agents, their tools and the reconciliation.
        log_text = log.path.read_text(encoding="utf-8")
        self.assertIn("| Collector   | TOOL CALL   | [step 1] load_transactions", log_text)
        self.assertIn("| Categorizer | TOOL CALL   | [step 1] load_cleaned_data", log_text)
        self.assertIn("61 loaded = 54 clean + 7 exceptions - OK", log_text)
        # The fake Collector's wrong first move was reported back, not crashed.
        self.assertTrue(re.search(r"Collector\s+\| TOOL ERROR", log_text))


if __name__ == "__main__":
    unittest.main()
