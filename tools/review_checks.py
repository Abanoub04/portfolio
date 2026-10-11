"""The Manager's review checks, run on the draft report before delivery.

All checks are plain Python, so they give the same answer every time.

a) Reconciliation
   1. Rows:   raw rows = clean rows + every row set aside (by reason)
   2. Totals: each category recalculated from the categorized data = the
              Analyst's figure; sum of categories = total expenses; every
              amount, and sales minus expenses, agree with the clean data.
   3. Report: every cell of the budget table = the Analyst's results; every
              number in the report appears in the Analyst's results; every
              percentage in the text belongs to the category it is next to.
b) Data quality (no answer key - these work on any client file)
   - every clean row is dated in the report month
   - no two clean rows share counterparty and amount within a few days
   - no positive amount from a supplier is counted as Sales
   - every row set aside by the Collector appears in the report
c) Claims
   Every sentence that explains a cause ("driven by", "linked to", ...) must
   cite source lines. The cited transactions must exist, belong to the
   categories the sentence talks about, and contain the names it uses
   (places, events, suppliers).

d) Deliverables (Excel, Word, PowerPoint)
   The files exist and were built from the current analysis and text; then
   each file is opened and its numbers are read back and compared with the
   Analyst's results (tools/deliverable_checks.py).

Each problem is returned as an issue with an owner:
   "writer" -> the report must be rewritten (sent back to the Writer)
   "data"   -> the data doesn't reconcile or fails a data-quality rule
               (the Manager must escalate; rewriting the report can't fix it)
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import config
from tools.csv_helpers import read_csv
from tools.data_rules import in_report_month, is_supplier_row, possible_duplicate_pairs
from tools.deliverable_checks import check_excel, check_slides, check_word
from tools.writer_tools import deliverables_source_hash
from tools.writer_tools import numbers_in

# Words that state a cause. One extra word may sit in between, so that
# "driven mainly by" or "linked directly to" are caught too.
CAUSE_WORDS = re.compile(
    r"\b(driven (?:\w+ )?by|due (?:\w+ )?to|because|caused (?:\w+ )?by|linked (?:\w+ )?to|"
    r"related (?:\w+ )?to|result of|explained (?:\w+ )?by|owing to|attributable to|reflects|"
    r"reflecting|thanks to)\b",
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
            self.issues.append({"owner": owner, "issue": issue, "check": check})

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
        self.check_period()
        self.check_possible_duplicates()
        self.check_supplier_sales()
        self.check_exceptions_in_report()
        self.check_report_table()
        self.check_report_numbers()
        self.check_percentages()
        self.check_claims()
        self.check_deliverables()

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
        raw, clean = len(self.raw_rows), len(self.clean)
        accounted = clean + sum(counts.values())
        # e.g. "61 raw rows = 54 clean + 4 probable duplicates + 3 missing amounts"
        plural = {"probable duplicate": "probable duplicates", "possible duplicate": "possible duplicates",
                  "missing amount": "missing amounts", "outside the period": "outside the period"}
        order = ["probable duplicate", "possible duplicate", "outside the period", "missing amount"]
        issues_in_order = order + sorted(issue for issue in counts if issue not in order)
        parts = [f"{counts[issue]} {issue if counts[issue] == 1 else plural.get(issue, issue)}"
                 for issue in issues_in_order if counts.get(issue)]
        detail = f"{raw} raw rows = {clean} clean" + "".join(f" + {part}" for part in parts)
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

        sales = money(self.analysis["totals"]["sales_income_czk"])
        if sales != recalculated.get("Sales", Decimal(0)):
            issues.append(f"Sales income {sales:,} differs from the categorized data "
                          f"{recalculated.get('Sales', Decimal(0)):,}")

        # Independent check straight from the Collector's clean file: every row
        # kept its amount, and sales minus expenses equals the net of all clean
        # amounts. (Works with refunds, which are positive amounts in expenses.)
        clean_amounts = {r["source_line"]: Decimal(r["amount_czk"]) for r in self.clean}
        changed = [r["source_line"] for r in self.categorized
                   if clean_amounts.get(r["source_line"]) != Decimal(r["amount_czk"])]
        if changed:
            issues.append(f"Amounts differ between the clean and categorized data on lines {changed}")
        net = sum(clean_amounts.values())
        if sales - total_expenses != net:
            issues.append(f"Sales {sales:,} minus expenses {total_expenses:,} does not equal the net of the "
                          f"clean data {net:,}")

        detail = (f"sum of {len(self.analysis['totals']['categories'])} categories = total expenses "
                  f"{self.analysis['totals']['total_expenses_czk']}; sales "
                  f"{self.analysis['totals']['sales_income_czk']}; every amount and the net agree with the clean data")
        self.record("Totals reconcile", not issues, detail if not issues else "; ".join(issues), "data", issues)

    # --- data quality (no answer key: works on any client file) ------------

    def check_period(self):
        outside = [f"line {r['source_line']} ({r['date']})" for r in self.clean if not in_report_month(r["date"])]
        issues = [f"Clean data contains rows dated outside {config.month_name()}: {', '.join(outside)}"] if outside else []
        self.record("Every clean row is dated in the report month", not issues,
                    f"{len(self.clean)} rows, all in {config.month_name()}", "data", issues)

    def check_possible_duplicates(self):
        pairs = possible_duplicate_pairs(self.clean)
        issues = [f"Lines {earlier['source_line']} and {row['source_line']} share counterparty "
                  f"{row['counterparty']} and amount {row['amount_czk']} within {config.DUPLICATE_WINDOW_DAYS} days"
                  for row, earlier in pairs]
        self.record("No possible duplicates left in the clean data", not issues,
                    f"no two rows share counterparty and amount within {config.DUPLICATE_WINDOW_DAYS} days",
                    "data", issues)

    def check_supplier_sales(self):
        issues = [f"Line {r['source_line']} ({r['description']}, {r['counterparty']}) is counted as Sales, "
                  f"but comes from a supplier"
                  for r in self.categorized
                  if r["category"] == "Sales" and Decimal(r["amount_czk"]) > 0 and is_supplier_row(r, self.clean)]
        sales_rows = sum(1 for r in self.categorized if r["category"] == "Sales")
        self.record("No supplier money counted as Sales", not issues,
                    f"{sales_rows} Sales rows, all customer income", "data", issues)

    def check_exceptions_in_report(self):
        section = self.report.split("## Exceptions", 1)[-1] if "## Exceptions" in self.report else ""
        listed = {int(n) for n in re.findall(r"^\| (\d+) \|", section, re.MULTILINE)}
        missing = [f"line {r['source_line']} ({r['issue']})" for r in self.exceptions
                   if int(r["source_line"]) not in listed]
        issues = [f"Set-aside rows missing from the report: {', '.join(missing)}"] if missing else []
        self.record("Every set-aside row appears in the report", not issues,
                    f"all {len(self.exceptions)} set-aside rows are listed", "data", issues)

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

    # --- d) deliverables --------------------------------------------------

    def check_deliverables(self):
        files = {kind: self.output_dir / name for kind, name in config.DRAFT_DELIVERABLES.items()}
        manifest = self.output_dir / config.DELIVERABLES_MANIFEST_FILE_NAME
        missing = [path.name for path in files.values() if not path.exists()]
        problems = []
        if missing or not manifest.exists():
            problems.append(f"Deliverable files missing ({', '.join(missing) or manifest.name}) - "
                            f"the Writer must run create_deliverables")
        elif json.loads(manifest.read_text(encoding="utf-8"))["source"] != deliverables_source_hash(self.output_dir):
            problems.append("Deliverable files are out of date (the analysis or text changed after they were "
                            "built) - the Writer must run create_deliverables again")
        self.record("Deliverables are present and up to date", not problems,
                    f"{', '.join(path.name for path in files.values())} built from the current analysis and text",
                    "writer", problems)
        if problems:
            self.record("Deliverables match the Analyst's results", False, "", "writer",
                        ["Not checked yet: the deliverable files are missing or out of date"])
            return

        texts = json.loads((self.output_dir / config.DRAFT_TEXTS_FILE_NAME).read_text(encoding="utf-8"))
        allowed = set(numbers_in(json.dumps(self.analysis, ensure_ascii=False)))
        mismatches = (check_excel(files["xlsx"], self.analysis, self.categorized, self.exceptions)
                      + check_word(files["docx"], self.analysis, self.exceptions, texts, allowed)
                      + check_slides(files["pptx"], self.analysis, allowed))
        # A wrong number in a generated file can't be fixed by rewriting the
        # text, so it is a data issue: the Manager must not deliver, and escalates.
        self.record("Deliverables match the Analyst's results", not mismatches,
                    "Excel, Word and PowerPoint read back: every number matches the Analyst's results",
                    "data", mismatches)

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
