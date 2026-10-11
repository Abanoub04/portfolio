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

import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import config

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

        report = self.build_report(summary.strip(), unusual_items_comment.strip(), exceptions_comment.strip())
        # Saved as a draft: only the Manager publishes the final report, after review.
        path = self.output_dir / config.DRAFT_REPORT_FILE_NAME
        path.write_text(report, encoding="utf-8")
        return {"file": path.name, "lines": report.count("\n") + 1, "number_check": "all numbers come from the analysis"}

    # --- building the report ----------------------------------------------

    def build_report(self, summary, unusual_items_comment, exceptions_comment):
        a = self.analysis
        month_name = datetime.strptime(a["report_month"], "%Y-%m").strftime("%B %Y")
        lines = [
            f"# Monthly expense report – {month_name}",
            "",
            f"All amounts in {a['currency']}. Prepared by LedgerMind.",
            "",
            "## Summary",
            "",
            summary,
            "",
        ]
        lines += self.budget_section()
        lines += self.unusual_section(unusual_items_comment)
        lines += self.exceptions_section(exceptions_comment)
        return "\n".join(lines).rstrip() + "\n"

    def budget_section(self):
        budget = self.analysis["budget_vs_actual"]
        totals = self.analysis["totals"]
        understated = self.analysis["exceptions"]["understated_categories"]
        lines = [
            "## Budget vs actual",
            "",
            "| Category | Actual | Budget | Variance | Variance % |",
            "|---|---:|---:|---:|---:|",
        ]
        for row in budget["categories"]:
            # A * marks categories whose actual is understated (amounts still missing).
            name = row["category"] + (" *" if row["category"] in understated else "")
            lines.append(f"| {name} | {row['actual_czk']} | {row['budget_czk']} | "
                         f"{row['variance_czk']} | {row['variance_percent']} |")
        total = budget["total"]
        lines.append(f"| **{total['category']}** | **{total['actual_czk']}** | **{total['budget_czk']}** | "
                     f"**{total['variance_czk']}** | **{total['variance_percent']}** |")
        lines.append("")
        if understated:
            parts = [f"{category} (line {', '.join(str(n) for n in found)})"
                     for category, found in understated.items()]
            lines += [f"\\* Actual understated – amount still missing for: {'; '.join(parts)}. "
                      f"See Exceptions.", ""]
        lines += [
            f"{budget['note']}.",
            "",
            f"Side note: sales income for the month was {totals['sales_income_czk']} "
            f"({totals['sales_transactions']} transactions).",
            "",
        ]
        return lines

    def unusual_section(self, comment):
        unusual = self.analysis["unusual_items"]
        lines = ["## Unusual items", ""]

        lines.append(f"**Categories more than {unusual['over_budget_threshold']} over budget**")
        lines.append("")
        if unusual["categories_over_budget"]:
            for item in unusual["categories_over_budget"]:
                largest = ", ".join(f"{x['description']} {x['amount_czk']}" for x in item.get("largest_items", []))
                lines.append(f"- **{item['category']}**: actual {item['actual_czk']} vs budget {item['budget_czk']} "
                             f"({item['variance_czk']}, {item['variance_percent']}). Largest items: {largest}.")
        else:
            lines.append("- None.")
        lines.append("")

        lines.append(f"**Categories more than {unusual['over_budget_threshold']} under budget**")
        lines.append("")
        if unusual["categories_under_budget"]:
            for item in unusual["categories_under_budget"]:
                lines.append(f"- **{item['category']}**: actual {item['actual_czk']} vs budget {item['budget_czk']} "
                             f"({item['variance_czk']}, {item['variance_percent']}). "
                             f"Note: {item['note']}.")
        else:
            lines.append("- None.")
        lines.append("")

        excluded = " and ".join(unusual["large_transactions_excluding"])
        lines.append(f"**Single expenses above {unusual['large_transaction_threshold_czk']} "
                     f"(excluding {excluded})**")
        lines.append("")
        if unusual["large_transactions"]:
            for item in unusual["large_transactions"]:
                lines.append(f"- Line {item['source_line']}, {item['date']}: {item['description']} "
                             f"({item['category']}) – {item['amount_czk']}")
        else:
            lines.append("- None.")
        lines.append("")

        if comment:
            lines += [comment, ""]
        return lines

    def exceptions_section(self, comment):
        exceptions = self.analysis["exceptions"]
        lines = ["## Exceptions", ""]

        lines.append(f"**Probable duplicates – confirm against the bank statement** "
                     f"({exceptions['probable_duplicates_count']}, total {exceptions['probable_duplicates_total_czk']}) – "
                     f"identical to an earlier row, so excluded from all totals above; if a row turns out "
                     f"to be a real separate charge, its amount must be added back")
        lines.append("")
        lines += self.table(["Line", "Date", "Description", "Amount", "Note"],
                            [[x["source_line"], x["date"], x["description"], x["amount_czk"], x["detail"]]
                             for x in exceptions["probable_duplicates"]])

        lines.append(f"**Missing amounts to follow up** ({exceptions['missing_amounts_count']}) – "
                     f"not included in the totals until the amount is known, so the actual "
                     f"of the likely category is understated")
        lines.append("")
        lines += self.table(["Line", "Date", "Description", "Counterparty", "Likely category"],
                            [[x["source_line"], x["date"], x["description"], x["counterparty"],
                              x["likely_category"]]
                             for x in exceptions["missing_amounts"]])

        lines.append(f"**Items needing review** ({exceptions['needs_review_count']}) – "
                     f"included in the totals, category to be confirmed")
        lines.append("")
        lines += self.table(["Line", "Date", "Description", "Category", "Amount", "To check"],
                            [[x["source_line"], x["date"], x["description"], x["category"],
                              x["amount_czk"], x["review_reason"]]
                             for x in exceptions["needs_review"]])

        if exceptions["other_issues"]:
            lines.append(f"**Other data issues** ({len(exceptions['other_issues'])})")
            lines.append("")
            lines += self.table(["Line", "Issue", "Detail"],
                                [[x["source_line"], x["issue"], x["detail"]] for x in exceptions["other_issues"]])

        if comment:
            lines += [comment, ""]
        return lines

    def table(self, headers, rows):
        if not rows:
            return ["None.", ""]
        lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        for row in rows:
            lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
        return lines + [""]


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
    ]
