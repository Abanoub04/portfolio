"""October 2026: a second test month with problems September didn't have.

Planted problems (see data/answer_key_2026-10.md):
  line 6   duplicate with slightly different wording (Adobe)  -> possible duplicate
  line 32  transaction dated in the wrong month (28.09.2026)  -> outside the period
  line 25  refund of a Travel expense (+3,100)                -> reduces Travel
  line 16  new supplier no keyword rule knows (Taskly)        -> decided by the AI

Also tests the Manager's data-quality checks, which use NO answer key: a
Collector with a planted bug must make the Manager escalate, not deliver.

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
from agents.collector import create_collector
from agents.manager import create_manager
from agents.simulated_ai import ManagerPolicy
from tools.collector_tools import TransactionCleaner
from tools.csv_helpers import read_csv
from tools.review_checks import ReportReview
from tools.run_checks import RunCheck


def run_october(output_dir, **options):
    with redirect_stdout(io.StringIO()):
        manager = create_manager(ActionLog(output_dir / "logs"), output_dir=output_dir, **options)
        manager.run("Prepare the October 2026 report.")
    return manager


class OctoberTestCase(unittest.TestCase):
    """Switches to October for the class, and back to September afterwards."""

    @classmethod
    def setUpClass(cls):
        config.set_month("2026-10")

    @classmethod
    def tearDownClass(cls):
        config.set_month(config.DEFAULT_MONTH)


class OctoberRunTests(OctoberTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temp_dir.name)
        cls.manager = run_october(cls.output_dir)
        cls.check = RunCheck(output_dir=cls.output_dir, outcome=cls.manager.desk.finished,
                             writer_runs=cls.manager.desk.writer_runs).run()
        cls.exceptions = {int(r["source_line"]): r for r in read_csv(cls.output_dir / config.EXCEPTIONS_FILE_NAME)}
        cls.categorized = {int(r["source_line"]): r
                           for r in read_csv(cls.output_dir / config.CATEGORIZED_FILE_NAME)}
        cls.report = (cls.output_dir / config.REPORT_FILE_NAME).read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        super().tearDownClass()

    def test_all_hard_checks_pass_and_report_is_delivered(self):
        failed = [c["check"] for c in self.check["hard"] if not c["passed"]]
        self.assertEqual(failed, [])
        self.assertEqual(len(self.check["hard"]), 13)
        self.assertEqual(self.manager.desk.finished, "delivered")

    def test_only_soft_difference_is_the_ai_choice_for_taskly(self):
        # The simulated AI books Taskly (1,750) in Other; the answer key says Software.
        # Everything else that differs follows from that one choice.
        differences = [s["detail"] for s in self.check["soft"] if not s["same"]]
        self.assertEqual(differences, [
            "line 16 Taskly team workspace (5 users): AI chose Other, answer key says Software "
            "(reason: Supplier not known to the keyword rules.)",
            "Software 13,860 vs answer key 15,610 (difference -1,750; see the cleaning and AI decisions above)",
            "Other 17,110 vs answer key 15,360 (difference +1,750; see the cleaning and AI decisions above)",
            "flagged ['Travel', 'Software', 'Marketing']; answer key ['Travel', 'Marketing', 'Other']",
        ])

    def test_reworded_duplicate_is_set_aside(self):
        self.assertEqual(self.exceptions[6]["issue"], "possible duplicate")
        self.assertIn("Same counterparty and amount as line 5", self.exceptions[6]["detail"])
        self.assertIn("confirm against the bank statement", self.exceptions[6]["detail"])

    def test_transaction_from_another_month_is_set_aside(self):
        self.assertEqual(self.exceptions[32]["issue"], "outside the period")
        self.assertNotIn(32, self.categorized)

    def test_refund_reduces_travel_and_is_flagged(self):
        refund = self.categorized[25]
        self.assertEqual(refund["category"], "Travel")
        self.assertEqual(refund["method"], "keyword")
        self.assertEqual(refund["needs_review"], "yes")
        self.assertIn("| Travel | 3,530 | 15,000 |", self.report)          # 6,630 spend - 3,100 refund

    def test_exceptions_section_lists_every_set_aside_row(self):
        section = self.report.split("## Exceptions", 1)[1]
        self.assertIn("**Possible duplicates – confirm against the bank statement** (1, total 5,400)", section)
        self.assertIn("| 6 | 2026-10-02 | Adobe CC subscription - 3 seats | 5,400 |", section)
        self.assertIn("**Outside the period** (1)", section)
        self.assertIn("| 32 | 2026-09-28 | Office supplies - printer toner | 1,560 |", section)
        self.assertIn("| 25 | 2026-10-14 | Refund - Hotel Berlin cancelled night | Travel (refund) | +3,100 |",
                      section)

    def test_october_files_do_not_overwrite_september(self):
        names = {path.name for path in self.output_dir.iterdir() if path.is_file()}
        self.assertTrue(names)
        self.assertTrue(all("2026-10" in name for name in names), names)


# --- The Manager's data-quality checks (no answer key) -------------------------

class LeakyCleaner(TransactionCleaner):
    """A Collector with planted bugs: no cut-off, no possible-duplicate check."""

    def set_aside_outside_period(self):
        self.done["period"] = True
        return {"outside_the_period_set_aside": [], "rows_remaining": len(self.rows)}

    def remove_duplicates(self):
        result = super().remove_duplicates()
        # Put the possible duplicates back into the clean data, as if never found.
        for row in [e for e in self.exceptions if e["issue"] == "possible duplicate"]:
            self.exceptions.remove(row)
            self.rows.append({k: v for k, v in row.items() if k not in ("issue", "detail")})
        return result


def leaky_collector(log, output_dir=None):
    return create_collector(log, output_dir=output_dir, cleaner=LeakyCleaner(output_dir=output_dir))


class DataQualityEscalationTests(OctoberTestCase):
    def test_manager_escalates_when_data_quality_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder)
            manager = run_october(output_dir, collector_factory=leaky_collector, fake_script=ManagerPolicy())
            notes = (output_dir / config.REVIEW_NOTES_FILE_NAME).read_text(encoding="utf-8")
            escalation = (output_dir / config.ESCALATION_FILE_NAME).read_text(encoding="utf-8")
            delivered = (output_dir / config.REPORT_FILE_NAME).exists()

        self.assertEqual(manager.desk.finished, "escalated")
        self.assertFalse(delivered)
        self.assertEqual(manager.desk.writer_runs, 1)     # data issues are not sent back to the Writer
        self.assertIn("[FAIL] Every clean row is dated in the report month", notes)
        self.assertIn("[FAIL] No possible duplicates left in the clean data", notes)
        self.assertIn("line 32 (2026-09-28)", escalation)
        self.assertIn("Lines 5 and 6 share counterparty Adobe Systems", escalation)


class DataQualityCheckTests(OctoberTestCase):
    """Each data-quality check on its own, by breaking one thing in a correct run."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        run_october(self.output_dir)
        (self.output_dir / config.DRAFT_REPORT_FILE_NAME).write_text(
            (self.output_dir / config.REPORT_FILE_NAME).read_text(encoding="utf-8"), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def failed(self):
        result = ReportReview(output_dir=self.output_dir).run()
        return {c["check"] for c in result["checks"] if not c["passed"]}, result

    def replace(self, name, old, new):
        path = self.output_dir / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_correct_run_passes(self):
        failed, result = self.failed()
        self.assertEqual(failed, set(), result["issues"])

    def test_row_from_another_month_is_caught(self):
        self.replace(config.CLEAN_FILE_NAME, "2026-10-20,Bank fees", "2026-11-02,Bank fees")
        failed, _ = self.failed()
        self.assertIn("Every clean row is dated in the report month", failed)

    def test_possible_duplicate_is_caught(self):
        # Make the Google Ads row (09.10) look like a second copy of the LinkedIn Ads row (15.10).
        self.replace(config.CLEAN_FILE_NAME, "2026-10-09,Google Ads October,Google Ireland,-9000.00",
                     "2026-10-14,Google Ads October,LinkedIn Ireland,-6000.00")
        failed, _ = self.failed()
        self.assertIn("No possible duplicates left in the clean data", failed)

    def test_supplier_money_in_sales_is_caught(self):
        self.replace(config.CATEGORIZED_FILE_NAME, "3100.00,Travel,", "3100.00,Sales,")
        failed, result = self.failed()
        self.assertIn("No supplier money counted as Sales", failed)
        self.assertTrue(all(i["owner"] == "data" for i in result["issues"]))

    def test_set_aside_row_missing_from_report_is_caught(self):
        self.replace(config.DRAFT_REPORT_FILE_NAME, "| 32 | 2026-09-28 |", "| removed | 2026-09-28 |")
        failed, _ = self.failed()
        self.assertIn("Every set-aside row appears in the report", failed)


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
