"""The Writer's tools: turn the Analyst's numbers into the monthly report.

Who writes what:
  - The Writer (the AI) writes the words: the summary and short comments.
  - Python builds every table and list straight from the Analyst's file,
    so those numbers are copied exactly, never retyped.

Number check: before the report is saved, every number in the AI's text
is compared with the numbers in the Analyst's file. If the AI wrote a
number that is not there (a rounded, calculated or invented one), the
report is NOT saved and the AI is told which number is wrong.
"""

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

import config
from tools.csv_helpers import read_csv
from tools.excel_report import build_workbook
from tools.report_content import build_content, month_name, render_markdown
from tools.slides_report import build_presentation
from tools.word_report import build_document

# A number like 42,000 or 68.0 or 17 (thousands separated by commas).
NUMBER_PATTERN = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def numbers_in(text):
    """All numbers in a text, as Decimal values ("42,000" -> 42000)."""
    return [Decimal(match.replace(",", "")) for match in NUMBER_PATTERN.findall(text)]


class ReportWriter:
    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        self.analysis = None

    def require_analysis(self):
        if self.analysis is None:
            raise RuntimeError("Read the analysis first (read_analysis)")

    # --- tools ------------------------------------------------------------

    def read_analysis(self):
        """Return the Analyst's results: the only source of numbers for the report."""
        path = self.output_dir / config.ANALYSIS_FILE_NAME
        if not path.exists():
            raise FileNotFoundError(f"{path.name} not found - the Analyst must run first")
        self.analysis = json.loads(path.read_text(encoding="utf-8"))
        return self.analysis

    def unknown_numbers(self, text):
        """Numbers in text that do not appear anywhere in the analysis."""
        allowed = set(numbers_in(json.dumps(self.analysis, ensure_ascii=False)))
        unknown = []
        for match, value in zip(NUMBER_PATTERN.findall(text), numbers_in(text)):
            if value not in allowed:
                unknown.append(match)
        return unknown

    def save_report(self, summary, unusual_items_comment, exceptions_comment=""):
        """Check the AI's text, build the report and save it."""
        self.require_analysis()

        texts = {"summary": summary, "unusual_items_comment": unusual_items_comment,
                 "exceptions_comment": exceptions_comment}
        problems = []
        for name, text in texts.items():
            unknown = self.unknown_numbers(text)
            if unknown:
                problems.append(f"{name}: {unknown}")
        if problems:
            raise ValueError("Report NOT saved. These numbers are not in the Analyst's output - "
                             "copy numbers exactly from read_analysis, never calculate or round: "
                             + "; ".join(problems))

        texts = {name: text.strip() for name, text in texts.items()}
        report = self.build_report(**texts)
        # Saved as a draft: only the Manager publishes the final report, after review.
        path = self.output_dir / config.DRAFT_REPORT_FILE_NAME
        path.write_text(report, encoding="utf-8")
        # The text parts are kept too: the Word, Excel and PowerPoint files are
        # built from exactly this text and the analysis.
        (self.output_dir / config.DRAFT_TEXTS_FILE_NAME).write_text(
            json.dumps(texts, indent=2, ensure_ascii=False), encoding="utf-8")
        # Files built from an earlier version of the text are now out of date.
        for name in list(config.DRAFT_DELIVERABLES.values()) + [config.DELIVERABLES_MANIFEST_FILE_NAME]:
            (self.output_dir / name).unlink(missing_ok=True)
        return {"file": path.name, "lines": report.count("\n") + 1, "number_check": "all numbers come from the analysis"}

    def create_deliverables(self):
        """Build the Excel, Word and PowerPoint files from the analysis and the
        saved draft text. Python writes every number; nothing is typed by the AI."""
        texts_path = self.output_dir / config.DRAFT_TEXTS_FILE_NAME
        if not texts_path.exists():
            raise RuntimeError("Save the report first (save_report); the files are built from its text")
        analysis = json.loads((self.output_dir / config.ANALYSIS_FILE_NAME).read_text(encoding="utf-8"))
        texts = json.loads(texts_path.read_text(encoding="utf-8"))
        categorized = read_csv(self.output_dir / config.CATEGORIZED_FILE_NAME)
        exceptions = read_csv(self.output_dir / config.EXCEPTIONS_FILE_NAME)
        label = month_name(analysis)

        files = {kind: self.output_dir / name for kind, name in config.DRAFT_DELIVERABLES.items()}
        build_workbook(analysis, categorized, exceptions, files["xlsx"], label)
        build_document(build_content(analysis, texts), files["docx"])
        build_presentation(analysis, texts, files["pptx"], label)

        # A fingerprint of what the files were built from, so the Manager can
        # tell if the text or the analysis changed afterwards.
        manifest = {"source": deliverables_source_hash(self.output_dir),
                    "files": {kind: path.name for kind, path in files.items()}}
        (self.output_dir / config.DELIVERABLES_MANIFEST_FILE_NAME).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        return {"files": [path.name for path in files.values()],
                "note": "Built by Python from the analysis and the saved text"}

    # --- building the report ----------------------------------------------

    def build_report(self, summary, unusual_items_comment, exceptions_comment):
        texts = {"summary": summary, "unusual_items_comment": unusual_items_comment,
                 "exceptions_comment": exceptions_comment}
        return render_markdown(build_content(self.analysis, texts))


def deliverables_source_hash(output_dir):
    """Fingerprint of the inputs of the deliverable files: analysis, draft text and data."""
    digest = hashlib.sha256()
    for name in [config.ANALYSIS_FILE_NAME, config.DRAFT_TEXTS_FILE_NAME,
                 config.CATEGORIZED_FILE_NAME, config.EXCEPTIONS_FILE_NAME]:
        path = Path(output_dir) / name
        digest.update(path.read_bytes() if path.exists() else b"-")
    return digest.hexdigest()


def make_writer_tools(writer):
    """The Writer's tool list."""
    return [
        {
            "name": "read_analysis",
            "description": "Read the Analyst's results. This is the only source of numbers for the report.",
            "input_schema": {"type": "object", "properties": {}},
            "function": writer.read_analysis,
        },
        {
            "name": "save_report",
            "description": "Build and save the report. You provide the text parts; the tables and lists are "
                           "added automatically from the analysis. Every number in your text must appear "
                           "exactly in the analysis, otherwise the report is rejected.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string",
                                "description": "Short summary for management, 3-5 sentences"},
                    "unusual_items_comment": {"type": "string",
                                              "description": "2-4 sentences explaining the unusual items"},
                    "exceptions_comment": {"type": "string",
                                           "description": "1-2 sentences on what must be followed up"},
                },
                "required": ["summary", "unusual_items_comment"],
            },
            "function": writer.save_report,
        },
        {
            "name": "create_deliverables",
            "description": "After save_report: build the client files (Excel, Word, PowerPoint) from the "
                           "analysis and the saved text. Python writes every number. Call it again after "
                           "every save_report.",
            "input_schema": {"type": "object", "properties": {}},
            "function": writer.create_deliverables,
        },
    ]
