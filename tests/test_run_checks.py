"""Tests for the run check: HARD checks vs SOFT differences (Stage 6).

Simulates what can happen with the real model: the AI categorizing a row
differently from the answer key (soft), and a real bug (hard).
Run from the project root with:   python -m unittest -v
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import config
from agents.action_log import ActionLog
from agents.manager import create_manager
from tests.test_manager import ESCALATION_SCRIPT, bad_writer
from tools.analyst_tools import ReportAnalyst
from tools.categorizer_tools import TransactionCategorizer
from tools.run_checks import RunCheck, format_run_check


class RunCheckTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        self.log = ActionLog(self.output_dir / "logs")

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_company(self, **options):
        with redirect_stdout(io.StringIO()):
            manager = create_manager(self.log, output_dir=self.output_dir, **options)
            manager.run("Prepare the September 2026 report.")
        return manager

    def check(self, manager=None):
        outcome = manager.desk.finished if manager else None
        writer_runs = manager.desk.writer_runs if manager else None
        return RunCheck(output_dir=self.output_dir, outcome=outcome, writer_runs=writer_runs).run()

    def differences(self, result):
        return [s for s in result["soft"] if not s["same"]]


class NormalRunTests(RunCheckTestCase):
    def test_test_mode_run_passes_all_hard_checks_with_no_differences(self):
        result = self.check(self.run_company())
        self.assertTrue(result["hard_passed"], format_run_check(result))
        self.assertEqual(len(result["hard"]), 16)
        self.assertEqual(self.differences(result), [])


class AiChoosesDifferentlyTests(RunCheckTestCase):
    """The AI puts the ALZA payment (line 43, 4,390 CZK) in Software instead of Other."""

    def setUp(self):
        super().setUp()
        self.run_company()
        categorizer = TransactionCategorizer(output_dir=self.output_dir)
        categorizer.load_cleaned_data()
        categorizer.apply_keyword_rules()
        categorizer.set_category(29, "Other", "Supermarket")
        categorizer.set_category(43, "Software", "Electronics retailer - treated as IT costs")
        categorizer.set_category(47, "Other", "Transfer", needs_review=True, review_reason="Confirm purpose")
        categorizer.save_categorized_data()
        analyst = ReportAnalyst(output_dir=self.output_dir)
        for step in [analyst.load_month_data, analyst.calculate_totals, analyst.compare_to_budget,
                     analyst.find_unusual_items, analyst.summarize_exceptions, analyst.save_analysis]:
            step()
        self.result = self.check()

    def test_category_choice_is_a_soft_difference(self):
        details = [s["detail"] for s in self.differences(self.result)]
        self.assertIn("line 43 Card payment 8812 - ALZA.CZ: AI chose Software, answer key says Other "
                      "(reason: Electronics retailer - treated as IT costs)", details)
        self.assertIn("Software 17,020 vs answer key 12,630 (difference +4,390; see the cleaning and AI decisions above)",
                      details)
        self.assertIn("Other 18,742 vs answer key 23,132 (difference -4,390; see the cleaning and AI decisions above)",
                      details)
        # Software is no longer more than 20% under budget (17,020 vs 18,000).
        self.assertIn("flagged none; answer key ['Software']", details)

    def test_data_hard_checks_still_pass(self):
        hard = {c["check"]: c["passed"] for c in self.result["hard"]}
        for name in ["Cleaning matches the answer key", "Every transaction has exactly one valid category",
                     "The AI only decided the unclear rows", "Total expenses and sales match the answer key",
                     "Rows reconcile", "Totals reconcile"]:
            self.assertTrue(hard[name], name)


class RealBugTests(RunCheckTestCase):
    def test_lost_clean_row_fails_hard_checks(self):
        self.run_company()
        clean = self.output_dir / config.CLEAN_FILE_NAME
        lines = clean.read_text(encoding="utf-8").splitlines()
        clean.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        result = self.check()
        self.assertFalse(result["hard_passed"])
        failed = [c["check"] for c in result["hard"] if not c["passed"]]
        self.assertIn("Rows reconcile", failed)
        self.assertIn("Totals reconcile", failed)
        self.assertIn("Cleaning matches the answer key", failed)


class EscalatedRunTests(RunCheckTestCase):
    def test_undelivered_draft_problems_are_reported_not_failed(self):
        manager = self.run_company(writer_factory=bad_writer, fake_script=ESCALATION_SCRIPT)
        result = self.check(manager)
        # The data is fine, and the bad draft was correctly not delivered.
        self.assertTrue(result["hard_passed"], format_run_check(result))
        text = format_run_check(result)
        self.assertIn("[DIFFERENT] Outcome: escalated; Writer revisions needed: 2 of 2", text)
        self.assertIn("[DIFFERENT] Last draft (not delivered): Percentages belong to the right category", text)
        self.assertIn("'Travel ... 68.0%' is wrong", text)


if __name__ == "__main__":
    unittest.main()
