"""The Manager's review checks, run on the draft report before delivery.

All checks are plain Python, so they give the same answer every time.

a) Reconciliation
   1. Rows:   raw rows = clean rows + duplicates + missing amounts (+ other issues)
   2. Totals: each category recalculated from the categorized data = the
              Analyst's figure; sum of categories = total expenses; total
              expenses and sales recalculated from the clean data agree.
   3. Report: every cell of the budget table = the Analyst's results; every
              number in the report appears in the Analyst's results; every
              percentage in the text belongs to the category it is next to.
b) Claims
   Every sentence that explains a cause ("driven by", "linked to", ...) must
   cite source lines. The cited transactions must exist, belong to the
   categories the sentence talks about, and contain the names it uses
   (places, events, suppliers).

Each problem is returned as an issue with an owner:
   "writer" -> the report must be rewritten (sent back to the Writer)
   "data"   -> the numbers themselves don't reconcile (escalate, don't rewrite)
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import config
from tools.csv_helpers import read_csv
from tools.writer_tools import numbers_in

CAUSE_WORDS = re.compile(
    r"\b(driven by|due to|because|caused by|linked to|related to|result of|explained by|"
    r"owing to|attributable to|reflects|reflecting|thanks to)\b",
    re.IGNORECASE,
)
CITATION = re.compile(r"\blines?\s+(\d+(?:\s*(?:,|and|&)\s*\d+)*)", re.IGNORECASE)
CATEGORY_NAME = re.compile(r"\b(" + "|".join(config.CATEGORIES) + r")\b")
PERCENT = re.compile(r"([+-]?\d+(?:\.\d+)?)%")
CAPITALIZED_WORD = re.compile(r"\b[A-Z][A-Za-z]+\b")

# Capitalized words that are ordinary report vocabulary, not names that need
# to be found in a cited transaction.
COMMON_WORDS = {
    "CZK", "No", "Both", "The", "This", "These", "That", "Total", "Note", "Side", "Line", "Lines",
    "Largest", "Actual", "Budget", "Variance", "Categories", "LedgerMind", "January", "February",
    "March", "April", "May", "June", "July", "August", "September", "October", "November", "December",
}


def money(text):
    """'42,000' or '-5,370' or '+10,546' -> Decimal."""
    return Decimal(text.replace(",", "").replace("+", ""))


def split_sentences(text):
    """Split text into sentences. A full stop inside a number (70.3) does not split."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def prose_lines(report):
    """The report's text lines without tables, headings or markdown symbols."""
    lines = []
    for line in report.splitlines():
        line = line.strip()
        if not line or line.startswith("|") or line.startswith("#"):
            continue
        lines.append(line.lstrip("-").replace("**", "").replace("\\*", "*").strip())
    return lines


class ReportReview:
    def __init__(self, output_dir=None, raw_file=None):
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        self.raw_file = Path(raw_file or config.TRANSACTIONS_FILE)
        self.checks = []   # list of {"check", "passed", "detail"}
        self.issues = []   # list of {"owner", "issue"}

    def record(self, check, passed, detail, owner=None, issues=()):
        # A failed check shows only how many issues it found; the issues
        # themselves are listed once, under "Issues found".
        if not passed:
            detail = f"{len(issues)} issue(s), see below"
        self.checks.append({"check": check, "passed": passed, "detail": detail})
        for issue in issues:
            self.issues.append({"owner": owner, "issue": issue})

    def run(self):
        """Run all checks. Returns {"passed", "checks", "issues"}."""
        out = self.output_dir
        self.raw_rows = read_csv(self.raw_file)
        self.clean = read_csv(out / config.CLEAN_FILE_NAME)
        self.exceptions = read_csv(out / config.EXCEPTIONS_FILE_NAME)
        self.categorized = read_csv(out / config.CATEGORIZED_FILE_NAME)
        self.analysis = json.loads((out / config.ANALYSIS_FILE_NAME).read_text(encoding="utf-8"))
        self.report = (out / config.DRAFT_REPORT_FILE_NAME).read_text(encoding="utf-8")

        self.check_rows()
        self.check_totals()
        self.check_report_table()
        self.check_report_numbers()
        self.check_percentages()
        self.check_claims()

        return {
            "passed": all(check["passed"] for check in self.checks),
            "checks": self.checks,
            "issues": self.issues,
        }

    # --- a) reconciliation ------------------------------------------------

    def check_rows(self):
        counts = {}
        for row in self.exceptions:
            counts[row["issue"]] = counts.get(row["issue"], 0) + 1
        duplicates = counts.pop("duplicate", 0)
        missing = counts.pop("missing amount", 0)
        other = sum(counts.values())

        raw, clean = len(self.raw_rows), len(self.clean)
        accounted = clean + duplicates + missing + other
        detail = (f"{raw} raw rows = {clean} clean + {duplicates} duplicates + {missing} missing amounts"
                  + (f" + {other} other issues" if other else ""))
        issues = []
        if raw != accounted:
            issues.append(f"Row reconciliation fails: {raw} raw rows but {accounted} accounted for")

        clean_lines = sorted(int(row["source_line"]) for row in self.clean)
        categorized_lines = sorted(int(row["source_line"]) for row in self.categorized)
        if clean_lines != categorized_lines:
            issues.append("The categorized data does not contain exactly the clean rows")

        self.record("Rows reconcile", not issues, detail if not issues else "; ".join(issues), "data", issues)

    def check_totals(self):
        issues = []

        # Each category, recalculated from the categorized rows.
        recalculated = {}
        for row in self.categorized:
            recalculated[row["category"]] = recalculated.get(row["category"], Decimal(0)) + Decimal(row["amount_czk"])

        category_sum = Decimal(0)
        for item in self.analysis["totals"]["categories"]:
            analyst_figure = money(item["actual_czk"])
            own_figure = -recalculated.get(item["category"], Decimal(0))
            category_sum += analyst_figure
            if analyst_figure != own_figure:
                issues.append(f"{item['category']}: Analyst says {item['actual_czk']}, "
                              f"recalculated from categorized data {own_figure:,}")

        total_expenses = money(self.analysis["totals"]["total_expenses_czk"])
        if category_sum != total_expenses:
            issues.append(f"Sum of categories {category_sum:,} differs from total expenses {total_expenses:,}")

        # Independent check straight from the Collector's clean file.
        clean_expenses = -sum(Decimal(r["amount_czk"]) for r in self.clean if Decimal(r["amount_czk"]) < 0)
        clean_income = sum(Decimal(r["amount_czk"]) for r in self.clean if Decimal(r["amount_czk"]) > 0)
        if clean_expenses != total_expenses:
            issues.append(f"Total expenses {total_expenses:,} differ from the clean data {clean_expenses:,}")
        sales = money(self.analysis["totals"]["sales_income_czk"])
        if clean_income != sales:
            issues.append(f"Sales income {sales:,} differs from the clean data {clean_income:,}")

        detail = (f"sum of {len(self.analysis['totals']['categories'])} categories = total expenses "
                  f"{self.analysis['totals']['total_expenses_czk']} = clean data; sales "
                  f"{self.analysis['totals']['sales_income_czk']} = clean data")
        self.record("Totals reconcile", not issues, detail if not issues else "; ".join(issues), "data", issues)

    def check_report_table(self):
        """Every cell of the budget table equals the Analyst's results."""
        expected = {row["category"]: row for row in self.analysis["budget_vs_actual"]["categories"]}
        total = self.analysis["budget_vs_actual"]["total"]
        expected[total["category"]] = total

        found = {}
        section = self.report.split("## Budget vs actual", 1)[-1].split("\n## ", 1)[0]
        for line in section.splitlines():
            if not line.startswith("|") or "---" in line or line.startswith("| Category"):
                continue
            cells = [cell.strip().replace("*", "").strip() for cell in line.strip("|").split("|")]
            found[cells[0]] = cells[1:]

        issues = []
        fields = ["actual_czk", "budget_czk", "variance_czk", "variance_percent"]
        for name, row in expected.items():
            if name not in found:
                issues.append(f"Budget table is missing the row '{name}'")
                continue
            for field, cell in zip(fields, found[name]):
                if cell != row[field]:
                    issues.append(f"Budget table, {name}: shows {cell}, Analyst says {row[field]}")
        cells_checked = len(expected) * len(fields)
        self.record("Budget table = Analyst's results", not issues,
                    f"{cells_checked} cells match" if not issues else "; ".join(issues), "writer", issues)

    def check_report_numbers(self):
        """Every number anywhere in the report appears in the Analyst's results."""
        allowed = set(numbers_in(json.dumps(self.analysis, ensure_ascii=False)))
        report_numbers = numbers_in(self.report)
        unknown = sorted({f"{n:,}" for n in report_numbers if n not in allowed})
        issues = [f"Number {n} in the report is not in the Analyst's results" for n in unknown]
        self.record("Every number comes from the Analyst", not issues,
                    f"{len(report_numbers)} numbers checked" if not issues else "; ".join(issues), "writer", issues)

    def check_percentages(self):
        """A percentage written next to a category must be that category's variance."""
        percent_of = {row["category"]: abs(Decimal(row["variance_percent"].rstrip("%")))
                      for row in self.analysis["budget_vs_actual"]["categories"]
                      if row["variance_percent"] != "n/a"}
        threshold = Decimal(str(config.OVER_BUDGET_THRESHOLD * 100))

        issues = []
        checked = 0
        for line in prose_lines(self.report):
            for sentence in split_sentences(line):
                # Walk through the sentence in order: remember the last category
                # named, and test each percentage against it.
                tokens = sorted(
                    [(m.start(), "category", m.group(1)) for m in CATEGORY_NAME.finditer(sentence)] +
                    [(m.start(), "percent", m.group(1)) for m in PERCENT.finditer(sentence)]
                )
                current = None
                for _, kind, value in tokens:
                    if kind == "category":
                        current = value
                    elif current in percent_of:
                        number = abs(Decimal(value))
                        checked += 1
                        if number not in (percent_of[current], threshold):
                            issues.append(f"'{current} ... {value}%' is wrong: {current} variance is "
                                          f"{percent_of[current]}% (in: \"{sentence}\")")
        self.record("Percentages belong to the right category", not issues,
                    f"{checked} percentages checked" if not issues else "; ".join(issues), "writer", issues)

    # --- b) claims --------------------------------------------------------

    def transaction(self, line_number):
        """Find a transaction by source line: in the categorized data or the
        exceptions (missing amounts count under their likely category)."""
        for row in self.categorized:
            if int(row["source_line"]) == line_number:
                return {"category": row["category"], "text": f"{row['description']} {row['counterparty']}"}
        for item in self.analysis["exceptions"]["missing_amounts"]:
            if item["source_line"] == line_number:
                return {"category": item["likely_category"], "text": f"{item['description']} {item['counterparty']}"}
        return None

    def check_claims(self):
        issues = []
        claims = []
        for line in prose_lines(self.report):
            for sentence in split_sentences(line):
                if not CAUSE_WORDS.search(sentence):
                    continue
                claims.append(sentence)
                issues += self.check_one_claim(sentence)

        self.record("Every cause is supported by cited transactions", not issues,
                    f"{len(claims)} cause explanations checked" if not issues else "; ".join(issues),
                    "writer", issues)

    def check_one_claim(self, sentence):
        quote = f"\"{sentence}\""
        cited = []
        for match in CITATION.finditer(sentence):
            cited += [int(n) for n in re.findall(r"\d+", match.group(1))]
        if not cited:
            return [f"Unsupported claim - no transactions cited: {quote}"]

        problems = []
        rows = {}
        for number in cited:
            row = self.transaction(number)
            if row is None:
                problems.append(f"Cited line {number} is not a transaction in this month's data: {quote}")
            else:
                rows[number] = row

        # The cited transactions must belong to the categories the sentence names.
        named = set(CATEGORY_NAME.findall(sentence))
        if named:
            for number, row in rows.items():
                if row["category"] not in named:
                    problems.append(f"Cited line {number} is {row['category']}, not "
                                    f"{' or '.join(sorted(named))}: {quote}")
            for category in named:
                if not any(row["category"] == category for row in rows.values()):
                    problems.append(f"No cited transaction supports the claim about {category}: {quote}")

        # Names used in the claim must appear in the cited transactions.
        evidence = " ".join(row["text"] for row in rows.values()).lower()
        words = CAPITALIZED_WORD.findall(sentence)[1:]   # skip the first word of the sentence
        for word in words:
            if word in COMMON_WORDS or word in config.CATEGORIES:
                continue
            if word.lower() not in evidence:
                problems.append(f"'{word}' does not appear in the cited transactions "
                                f"(lines {', '.join(map(str, cited))}): {quote}")
        return problems


def format_review(result, title):
    """Turn a review result into markdown for the review notes."""
    status = "PASSED" if result["passed"] else "FAILED"
    lines = [f"## {title} – {status}", ""]
    for check in result["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- [{mark}] {check['check']}: {check['detail']}")
    lines.append("")
    return "\n".join(lines)
