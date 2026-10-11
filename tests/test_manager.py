"""Tests for the Manager (Stage 5): delegation, review, delivery and escalation.

Includes the planted-mistake tests: a wrong claim and a wrong number are
put into the report, and the Manager must catch both.
Run from the project root with:   python -m unittest -v
"""

import os
import shutil
import tempfile
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from unittest import mock

import config
from agents.action_log import ActionLog
from agents.manager import create_manager
from agents.writer import EXCEPTIONS, SUMMARY, UNUSUAL_REVISED, create_writer
from tests.test_reporting import as_decimal, read_answer_key, report_table_rows
from tools.manager_tools import ManagerDesk
from tools.review_checks import ReportReview

# --- The planted mistakes ------------------------------------------------------
# Wrong number: Travel's variance is 70.3%, the report says 68.0% (Marketing's).
# It passes the Writer's own check (68.0 IS in the analysis), so only the
# Manager's review can catch it.
WRONG_NUMBER_SUMMARY = SUMMARY.replace("Travel (70.3%)", "Travel (68.0%)")
assert WRONG_NUMBER_SUMMARY != SUMMARY, "the planted mistake must change the text"
# Wrong claim: line 38 is the Berlin hotel (Travel), not a Prague trade fair.
WRONG_CLAIM = " Marketing was also driven by the Prague trade fair (line 38)."

BAD_WRITER_SCRIPT = [
    {"tool": "read_analysis"},
    {"tool": "save_report", "input": {
        "summary": WRONG_NUMBER_SUMMARY,
        "unusual_items_comment": UNUSUAL_REVISED + WRONG_CLAIM,
        "exceptions_comment": EXCEPTIONS}},
    {"tool": "create_deliverables"},
    {"text": "Saved."},
]


def bad_writer(log, output_dir=None, revision=0):
    """A Writer that makes the same two mistakes every time."""
    return create_writer(log, output_dir=output_dir, revision=revision, fake_script=BAD_WRITER_SCRIPT)


def good_writer(log, output_dir=None, revision=0):
    """A Writer whose first draft is already correct."""
    return create_writer(log, output_dir=output_dir, revision=1)


FEEDBACK = "Fix the Travel percentage and the unsupported Prague claim."
ESCALATION_SCRIPT = [
    {"tool": "ask_collector"},
    {"tool": "ask_categorizer"},
    {"tool": "ask_analyst"},
    {"tool": "ask_writer"},
    {"tool": "review_report"},
    {"tool": "ask_writer", "input": {"feedback": FEEDBACK}},
    {"tool": "review_report"},
    {"tool": "ask_writer", "input": {"feedback": FEEDBACK}},
    {"tool": "review_report"},
    {"tool": "ask_writer", "input": {"feedback": FEEDBACK}},       # a 3rd revision: must be refused
    {"tool": "deliver_report", "input": {"note": "Trying anyway"}},  # must be refused
    {"tool": "escalate_to_owner", "input": {
        "summary": "The report still fails review after 2 revisions.",
        "issues": ["Travel percentage is wrong", "Unsupported claim about a Prague trade fair"]}},
    {"text": "Not delivered - escalated to the owner."},
]


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        self.log = ActionLog(self.output_dir / "logs")

    def tearDown(self):
        self.temp_dir.cleanup()

    def read(self, name):
        return (self.output_dir / name).read_text(encoding="utf-8")


@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
class ManagerDeliversTests(TempDirTestCase):
    """The normal run: one send-back, then delivery."""

    def setUp(self):
        super().setUp()
        self.manager = create_manager(self.log, output_dir=self.output_dir)
        self.answer = self.manager.run("Prepare the September 2026 report.")

    def test_report_is_delivered_after_one_revision(self):
        self.assertEqual(self.manager.desk.finished, "delivered")
        self.assertEqual(self.manager.desk.writer_runs, 2)
        self.assertEqual(self.read(config.REPORT_FILE_NAME), self.read(config.DRAFT_REPORT_FILE_NAME))
        self.assertFalse((self.output_dir / config.ESCALATION_FILE_NAME).exists())

    def test_review_notes_show_both_rounds(self):
        notes = self.read(config.REVIEW_NOTES_FILE_NAME)
        self.assertIn("## Review 1 (first draft) – FAILED", notes)
        self.assertIn("Unsupported claim - no transactions cited", notes)
        self.assertIn("## Review 2 (revision 1) – PASSED", notes)
        self.assertIn("[PASS] Rows reconcile: 61 raw rows = 54 clean + 4 probable duplicates + 3 missing amounts", notes)
        self.assertIn("## Delivered", notes)

    def test_delivered_report_matches_answer_key(self):
        key = read_answer_key()
        table = report_table_rows(self.read(config.REPORT_FILE_NAME))
        for name in ["Salaries", "Rent", "Travel", "Software", "Marketing", "Utilities", "Other", "Total expenses"]:
            with self.subTest(name=name):
                actual, budget, variance, percent = table[name]
                self.assertEqual(as_decimal(actual), key[name]["actual"])
                self.assertEqual(as_decimal(budget), key[name]["budget"])
                self.assertEqual(as_decimal(variance), key[name]["actual"] - key[name]["budget"])
                self.assertEqual(as_decimal(percent).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                                 key[name]["percent"])

    def test_every_agent_appears_in_the_log(self):
        log_text = self.log.path.read_text(encoding="utf-8")
        for agent in ["Manager", "Collector", "Categorizer", "Analyst", "Writer"]:
            self.assertIn(f"| {agent:<11} | START", log_text)


@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
class ManagerCatchesPlantedMistakesTests(TempDirTestCase):
    """A Writer that always plants a wrong claim and a wrong number."""

    def setUp(self):
        super().setUp()
        self.manager = create_manager(self.log, output_dir=self.output_dir,
                                      writer_factory=bad_writer, fake_script=ESCALATION_SCRIPT)
        self.manager.run("Prepare the September 2026 report.")
        self.notes = self.read(config.REVIEW_NOTES_FILE_NAME)
        self.log_text = self.log.path.read_text(encoding="utf-8")

    def test_wrong_number_is_caught_in_every_review(self):
        self.assertEqual(self.notes.count("'Travel ... 68.0%' is wrong: Travel variance is 70.3%"), 3)

    def test_wrong_claim_is_caught_in_every_review(self):
        self.assertEqual(self.notes.count("Cited line 38 is Travel, not Marketing"), 3)
        self.assertEqual(self.notes.count("'Prague' does not appear in the cited transactions"), 3)

    def test_sent_back_at_most_twice_then_escalated(self):
        self.assertEqual(self.manager.desk.writer_runs, 3)          # draft + 2 revisions
        self.assertIn("No more revisions - escalate to the owner instead", self.log_text)
        self.assertIn("Cannot deliver: the latest review did not pass", self.log_text)
        self.assertEqual(self.manager.desk.finished, "escalated")

    def test_nothing_is_delivered(self):
        self.assertFalse((self.output_dir / config.REPORT_FILE_NAME).exists())
        escalation = self.read(config.ESCALATION_FILE_NAME)
        self.assertIn("NOT delivered", escalation)
        self.assertIn("Unsupported claim about a Prague trade fair", escalation)
        # The exact review findings are attached by code, not left to the Manager.
        self.assertIn("## Findings of the last review (review 3)", escalation)
        self.assertIn("'Travel ... 68.0%' is wrong", escalation)
        self.assertIn("'Prague' does not appear in the cited transactions", escalation)


@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
class ReviewCheckTests(TempDirTestCase):
    """Each review check on its own, using a correct draft that is then tampered with."""

    def setUp(self):
        super().setUp()
        self.desk = ManagerDesk(self.log, output_dir=self.output_dir, writer_factory=good_writer)
        self.desk.ask_collector()
        self.desk.ask_categorizer()
        self.desk.ask_analyst()
        self.desk.ask_writer()
        self.draft = self.output_dir / config.DRAFT_REPORT_FILE_NAME

    def review(self):
        return ReportReview(output_dir=self.output_dir).run()

    def failed_checks(self, result):
        return [check["check"] for check in result["checks"] if not check["passed"]]

    def tamper(self, old, new):
        text = self.draft.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.draft.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_correct_draft_passes(self):
        result = self.review()
        self.assertTrue(result["passed"], result["issues"])

    def test_planted_wrong_number_in_table_is_caught(self):
        self.tamper("| Travel * | 25,546 |", "| Travel * | 25,456 |")
        result = self.review()
        self.assertFalse(result["passed"])
        self.assertIn("Budget table = Analyst's results", self.failed_checks(result))
        self.assertIn("Every number comes from the Analyst", self.failed_checks(result))
        self.assertTrue(any("Travel: shows 25,456, Analyst says 25,546" in i["issue"] for i in result["issues"]))

    def test_planted_wrong_claim_is_caught(self):
        self.tamper("exceeded 20,000 CZK.", "exceeded 20,000 CZK." + WRONG_CLAIM)
        result = self.review()
        self.assertEqual(self.failed_checks(result), ["Every cause is supported by cited transactions"])

    def test_cause_with_extra_word_is_still_a_claim(self):
        # "driven mainly by" must be recognised as a cause, like "driven by".
        self.tamper("exceeded 20,000 CZK.", "exceeded 20,000 CZK. Travel was driven mainly by the Berlin trip.")
        result = self.review()
        self.assertTrue(any("no transactions cited" in i["issue"] and "driven mainly by" in i["issue"]
                            for i in result["issues"]))

    def test_cause_without_citation_is_caught(self):
        self.tamper("(lines 37, 38, 40)", "")
        result = self.review()
        self.assertTrue(any("no transactions cited" in i["issue"] for i in result["issues"]))

    def test_broken_reconciliation_is_a_data_issue(self):
        clean = self.output_dir / config.CLEAN_FILE_NAME
        lines = clean.read_text(encoding="utf-8").splitlines()
        clean.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")   # lose one clean row
        result = self.review()
        owners = {i["owner"] for i in result["issues"]}
        self.assertIn("Rows reconcile", self.failed_checks(result))
        self.assertIn("Totals reconcile", self.failed_checks(result))
        self.assertEqual(owners, {"data"})

    def test_cannot_deliver_without_passed_review(self):
        with self.assertRaises(RuntimeError):
            self.desk.deliver_report("note")

    def test_cannot_deliver_if_draft_changed_after_review(self):
        self.assertTrue(self.desk.review_report()["passed"])
        self.tamper("Prepared by LedgerMind.", "Prepared by LedgerMind. Edited.")
        with self.assertRaises(RuntimeError):
            self.desk.deliver_report("note")

    def test_revision_needs_feedback(self):
        with self.assertRaises(ValueError):
            self.desk.ask_writer("")

    def test_delivery_copies_the_reviewed_draft(self):
        self.desk.review_report()
        self.desk.deliver_report("All checks passed.")
        self.assertEqual(self.read(config.REPORT_FILE_NAME), self.draft.read_text(encoding="utf-8"))
        with self.assertRaises(RuntimeError):
            self.desk.ask_writer("more changes")   # job is finished


if __name__ == "__main__":
    unittest.main()
