"""The Manager's tools: delegate to the departments, review, deliver or escalate.

Each department agent is called like a tool (ask_collector, ask_writer, ...).
The rules that protect the owner are enforced here in code, whatever the
Manager (the AI) decides:
  - The Writer may be sent back at most config.MAX_REVISIONS times.
  - A report can only be delivered after a review of exactly that draft passed.
  - After an escalation, nothing can be delivered.
"""

import hashlib
import shutil
from pathlib import Path

import config
from agents.analyst import TASK as ANALYST_TASK, create_analyst
from agents.categorizer import TASK as CATEGORIZER_TASK, create_categorizer
from agents.collector import TASK as COLLECTOR_TASK, create_collector
from agents.writer import create_writer, writer_task
from tools.review_checks import ReportReview, format_review


class ManagerDesk:
    def __init__(self, log, output_dir=None, writer_factory=create_writer):
        self.log = log
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        # Tests pass a different writer_factory to plant mistakes in the report.
        self.writer_factory = writer_factory

        self.writer_runs = 0          # 1 = first draft, 2+ = revisions
        self.last_review = None       # {"passed": bool, "draft_hash": str}
        self.review_rounds = 0
        self.finished = None          # "delivered" or "escalated"

        # Start clean: remove the Manager's files from an earlier run, so an
        # old report can never be mistaken for this run's result.
        for name in [config.DRAFT_REPORT_FILE_NAME, config.REPORT_FILE_NAME,
                     config.REVIEW_NOTES_FILE_NAME, config.ESCALATION_FILE_NAME]:
            (self.output_dir / name).unlink(missing_ok=True)

    # --- helpers ----------------------------------------------------------

    def path(self, name):
        return self.output_dir / name

    def draft_hash(self):
        """A fingerprint of the draft, to know if it changed after the review."""
        draft = self.path(config.DRAFT_REPORT_FILE_NAME)
        if not draft.exists():
            return None
        return hashlib.sha256(draft.read_bytes()).hexdigest()

    def add_to_review_notes(self, text):
        notes = self.path(config.REVIEW_NOTES_FILE_NAME)
        if not notes.exists():
            notes.write_text(f"# Review notes – report {config.REPORT_MONTH}\n\n", encoding="utf-8")
        with open(notes, "a", encoding="utf-8") as file:
            file.write(text.rstrip() + "\n\n")

    def require_not_finished(self):
        if self.finished:
            raise RuntimeError(f"The job is already {self.finished}")

    # --- delegation tools ---------------------------------------------------

    def ask_collector(self):
        self.require_not_finished()
        answer = create_collector(self.log, output_dir=self.output_dir).run(COLLECTOR_TASK)
        return {"agent": "Collector", "answer": answer}

    def ask_categorizer(self):
        self.require_not_finished()
        answer = create_categorizer(self.log, output_dir=self.output_dir).run(CATEGORIZER_TASK)
        return {"agent": "Categorizer", "answer": answer}

    def ask_analyst(self):
        self.require_not_finished()
        answer = create_analyst(self.log, output_dir=self.output_dir).run(ANALYST_TASK)
        return {"agent": "Analyst", "answer": answer}

    def ask_writer(self, feedback=""):
        """First call: write the draft. Later calls: rewrite it using the feedback."""
        self.require_not_finished()
        revision = self.writer_runs   # 0 for the first draft
        if revision > config.MAX_REVISIONS:
            raise RuntimeError(f"The report was already sent back {config.MAX_REVISIONS} times. "
                               f"No more revisions - escalate to the owner instead.")
        if revision > 0 and not feedback.strip():
            raise ValueError("A revision needs feedback: say exactly what the Writer must fix")

        self.writer_runs += 1
        writer = self.writer_factory(self.log, output_dir=self.output_dir, revision=revision)
        answer = writer.run(writer_task(feedback, revision))
        label = "first draft" if revision == 0 else f"revision {revision} of {config.MAX_REVISIONS}"
        return {"agent": "Writer", "draft": label, "answer": answer,
                "revisions_left": config.MAX_REVISIONS - revision}

    # --- review, delivery, escalation ---------------------------------------

    def review_report(self):
        """Run every reconciliation and claim check on the current draft."""
        self.require_not_finished()
        if self.draft_hash() is None:
            raise FileNotFoundError("There is no draft report yet - ask the Writer first")

        result = ReportReview(output_dir=self.output_dir).run()
        self.review_rounds += 1
        self.last_review = {"passed": result["passed"], "draft_hash": self.draft_hash(),
                            "issues": result["issues"]}

        draft = "first draft" if self.writer_runs <= 1 else f"revision {self.writer_runs - 1}"
        notes = format_review(result, f"Review {self.review_rounds} ({draft})")
        if result["issues"]:
            notes = notes.rstrip() + "\n\nIssues found:\n" + "\n".join(f"- ({i['owner']}) {i['issue']}" for i in result["issues"])
        self.add_to_review_notes(notes)

        return {
            "passed": result["passed"],
            "checks": [f"[{'PASS' if c['passed'] else 'FAIL'}] {c['check']}: {c['detail']}"
                       for c in result["checks"]],
            "issues_for_writer": [i["issue"] for i in result["issues"] if i["owner"] == "writer"],
            "data_issues": [i["issue"] for i in result["issues"] if i["owner"] == "data"],
            "revisions_left": max(0, config.MAX_REVISIONS - max(0, self.writer_runs - 1)),
        }

    def deliver_report(self, note):
        """Publish the reviewed draft as the final report, with the Manager's note."""
        self.require_not_finished()
        if not self.last_review or not self.last_review["passed"]:
            raise RuntimeError("Cannot deliver: the latest review did not pass")
        if self.draft_hash() != self.last_review["draft_hash"]:
            raise RuntimeError("Cannot deliver: the draft changed after the review - review it again")

        shutil.copyfile(self.path(config.DRAFT_REPORT_FILE_NAME), self.path(config.REPORT_FILE_NAME))
        self.add_to_review_notes(f"## Delivered\n\n{note.strip()}")
        self.finished = "delivered"
        return {"delivered": config.REPORT_FILE_NAME, "review_notes": config.REVIEW_NOTES_FILE_NAME}

    def escalate_to_owner(self, summary, issues):
        """Stop without delivering, and tell the owner what is wrong."""
        self.require_not_finished()
        lines = [f"# Escalation – report {config.REPORT_MONTH} NOT delivered", "", summary.strip(), "",
                 "## Open issues", ""]
        lines += [f"- {issue}" for issue in issues]
        # The exact findings of the last review, added by code, so the owner
        # always gets the full list - whatever the Manager wrote above.
        if self.last_review and self.last_review["issues"]:
            lines += ["", f"## Findings of the last review (review {self.review_rounds})", ""]
            lines += [f"- ({i['owner']}) {i['issue']}" for i in self.last_review["issues"]]
        lines += ["", f"The last draft is in {config.DRAFT_REPORT_FILE_NAME}; "
                      f"the full review history is in {config.REVIEW_NOTES_FILE_NAME}."]
        self.path(config.ESCALATION_FILE_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.add_to_review_notes(f"## Escalated to the owner – NOT delivered\n\n{summary.strip()}")
        self.finished = "escalated"
        return {"escalated": config.ESCALATION_FILE_NAME, "issues": len(issues)}


def make_manager_tools(desk):
    no_inputs = {"type": "object", "properties": {}}
    return [
        {"name": "ask_collector", "description": "Bookkeeping: have the Collector clean the raw transactions.",
         "input_schema": no_inputs, "function": desk.ask_collector},
        {"name": "ask_categorizer", "description": "Bookkeeping: have the Categorizer categorize the clean data.",
         "input_schema": no_inputs, "function": desk.ask_categorizer},
        {"name": "ask_analyst", "description": "Reporting: have the Analyst calculate all report numbers.",
         "input_schema": no_inputs, "function": desk.ask_analyst},
        {
            "name": "ask_writer",
            "description": f"Reporting: have the Writer write the draft report. Call again with feedback to "
                           f"send the report back (at most {config.MAX_REVISIONS} times).",
            "input_schema": {
                "type": "object",
                "properties": {"feedback": {"type": "string",
                                            "description": "For a revision: exactly what must be fixed"}},
            },
            "function": desk.ask_writer,
        },
        {"name": "review_report",
         "description": "Review the current draft: reconciliation of rows and totals, report numbers against "
                        "the Analyst's results, and whether every stated cause is supported by transactions.",
         "input_schema": no_inputs, "function": desk.review_report},
        {
            "name": "deliver_report",
            "description": "Deliver the reviewed report to the owner. Only works if the latest review passed.",
            "input_schema": {
                "type": "object",
                "properties": {"note": {"type": "string",
                                        "description": "Short note to the owner on what was checked"}},
                "required": ["note"],
            },
            "function": desk.deliver_report,
        },
        {
            "name": "escalate_to_owner",
            "description": "Do NOT deliver; report the open issues to the owner instead.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Why the report cannot be delivered"},
                    "issues": {"type": "array", "items": {"type": "string"},
                               "description": "Each open issue, one per item"},
                },
                "required": ["summary", "issues"],
            },
            "function": desk.escalate_to_owner,
        },
    ]
