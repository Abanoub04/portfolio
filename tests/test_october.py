"""October 2026: a second test month with problems September didn't have.

Planted problems (see data/answer_key_2026-10.md):
  line 6   duplicate with slightly different wording (Adobe)
  line 32  transaction dated in the wrong month (28.09.2026)
  line 25  refund of a Travel expense (+3,100)
  line 16  new supplier no keyword rule knows (Taskly)

The first group of tests records what the company does TODAY. The "known
gap" tests describe what it SHOULD do; they are marked expectedFailure, so
they show up as "expected failures" until the gap is fixed (then they
report "unexpected success" and the marker can be removed).

Run from the project root with:   python -m unittest -v
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import config
from agents import models
from agents.action_log import ActionLog
from agents.manager import create_manager
from tools.csv_helpers import read_csv
from tools.run_checks import RunCheck


class OctoberRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.set_month("2026-10")
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temp_dir.name)
        with redirect_stdout(io.StringIO()):
            cls.manager = create_manager(ActionLog(cls.output_dir / "logs"), output_dir=cls.output_dir)
            cls.manager.run("Prepare the October 2026 report.")
        cls.check = RunCheck(output_dir=cls.output_dir, outcome=cls.manager.desk.finished,
                             writer_runs=cls.manager.desk.writer_runs).run()
        cls.hard = {c["check"]: c for c in cls.check["hard"]}
        cls.exceptions = {int(r["source_line"]): r for r in read_csv(cls.output_dir / config.EXCEPTIONS_FILE_NAME)}
        cls.categorized = {int(r["source_line"]): r
                           for r in read_csv(cls.output_dir / config.CATEGORIZED_FILE_NAME)}

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        config.set_month(config.DEFAULT_MONTH)

    # --- What happens today -------------------------------------------------

    def test_manager_delivers_because_its_internal_checks_pass(self):
        self.assertEqual(self.manager.desk.finished, "delivered")
        notes = (self.output_dir / config.REVIEW_NOTES_FILE_NAME).read_text(encoding="utf-8")
        self.assertIn("## Review 1 (first draft) – PASSED", notes)

    def test_internal_reconciliation_and_report_checks_pass(self):
        for name in ["Rows reconcile", "Totals reconcile", "Budget table = Analyst's results",
                     "Every number comes from the Analyst", "Percentages belong to the right category",
                     "Every transaction has exactly one valid category", "The AI only decided the unclear rows"]:
            self.assertTrue(self.hard[name]["passed"], name)

    def test_comparison_with_the_answer_key_fails(self):
        failed = [c["check"] for c in self.check["hard"] if not c["passed"]]
        self.assertEqual(failed, ["Cleaning matches the answer key",
                                  "Total expenses and sales match the answer key"])
        # +10,060 = duplicate 5,400 + September toner 1,560 + refund not netted 3,100
        self.assertIn("total expenses 581,546 vs answer key 571,486 (difference +10,060)",
                      self.hard["Total expenses and sales match the answer key"]["detail"])
        self.assertIn("sales 251,600 vs answer key 248,500 (difference +3,100)",
                      self.hard["Total expenses and sales match the answer key"]["detail"])

    def test_refund_and_new_supplier_are_flagged_for_review(self):
        self.assertEqual(self.categorized[25]["category"], "Sales")      # refund: forced into Sales
        self.assertEqual(self.categorized[16]["category"], "Other")      # Taskly: simulated AI guesses Other
        self.assertEqual(self.categorized[25]["needs_review"], "yes")
        self.assertEqual(self.categorized[16]["needs_review"], "yes")
        report = (self.output_dir / config.REPORT_FILE_NAME).read_text(encoding="utf-8")
        self.assertIn("Probably a refund of a Travel expense", report)

    def test_october_files_do_not_overwrite_september(self):
        names = {path.name for path in self.output_dir.iterdir() if path.is_file()}
        self.assertTrue(names)
        self.assertTrue(all("2026-10" in name for name in names), names)

    # --- Known gaps: what the company SHOULD do -------------------------------

    @unittest.expectedFailure
    def test_known_gap_reworded_duplicate_is_set_aside(self):
        """KNOWN GAP: duplicates are only found when every field is identical.
        Line 6 is the Adobe charge of line 5 with different wording."""
        self.assertEqual(self.exceptions[6]["issue"], "probable duplicate")

    @unittest.expectedFailure
    def test_known_gap_transaction_from_another_month_is_set_aside(self):
        """KNOWN GAP: the Collector does not check that dates are in the report month.
        Line 32 is dated 28.09.2026 and ends up in the October totals."""
        self.assertEqual(self.exceptions[32]["issue"], "outside period")

    @unittest.expectedFailure
    def test_known_gap_refund_reduces_travel(self):
        """KNOWN GAP: the sign rule allows positive amounts only in Sales, so a refund
        can't reduce its expense category - it is pushed into Sales instead."""
        self.assertEqual(self.categorized[25]["category"], "Travel")


class SimulatedAiOnSeptemberTests(unittest.TestCase):
    """The simulated AI used for other months, tried on September (where the
    answer is known): it must deliver a report that passes every check."""

    def test_simulated_manager_and_writer_on_september(self):
        from agents.simulated_ai import ManagerPolicy, WriterPolicy
        from agents.writer import create_writer

        def writer(log, output_dir=None, revision=0):
            return create_writer(log, output_dir=output_dir, fake_script=WriterPolicy())

        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            output_dir = Path(folder)
            manager = create_manager(ActionLog(output_dir / "logs"), output_dir=output_dir,
                                     writer_factory=writer, fake_script=ManagerPolicy())
            manager.run("Prepare the September 2026 report.")
            check = RunCheck(output_dir=output_dir, outcome=manager.desk.finished,
                             writer_runs=manager.desk.writer_runs).run()
            notes = (output_dir / config.REVIEW_NOTES_FILE_NAME).read_text(encoding="utf-8")

        self.assertEqual(manager.desk.finished, "delivered")
        self.assertTrue(check["hard_passed"])
        self.assertEqual([s for s in check["soft"] if not s["same"]], [])
        self.assertIn("2 cause explanations checked", notes)


class MonthAndTestSwitchTests(unittest.TestCase):
    def tearDown(self):
        config.set_month(config.DEFAULT_MONTH)
        models.test_mode_forced = False

    def test_set_month_changes_every_file_name(self):
        config.set_month("2026-10")
        self.assertEqual(config.TRANSACTIONS_FILE.name, "transactions_2026-10.csv")
        for name in [config.CLEAN_FILE_NAME, config.EXCEPTIONS_FILE_NAME, config.CATEGORIZED_FILE_NAME,
                     config.ANALYSIS_FILE_NAME, config.DRAFT_REPORT_FILE_NAME, config.REPORT_FILE_NAME,
                     config.REVIEW_NOTES_FILE_NAME, config.ESCALATION_FILE_NAME, config.RUN_CHECK_FILE_NAME]:
            self.assertIn("2026-10", name)
        self.assertEqual(config.month_name(), "October 2026")

    def test_september_keeps_its_original_file(self):
        self.assertEqual(config.TRANSACTIONS_FILE.name, "transactions.csv")

    def test_test_switch_wins_over_a_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-not-a-real-key"}):
            self.assertTrue(models.using_real_model())
            models.force_test_mode()
            self.assertFalse(models.using_real_model())
            self.assertIsInstance(models.create_model(), models.FakeModel)


if __name__ == "__main__":
    unittest.main()
