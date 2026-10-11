"""Checks after a full run, split into HARD checks and SOFT differences.

With the real model, the AI's choices can differ between runs (e.g. which
category it gives the ALZA card payment). So the results are split:

HARD checks - must ALWAYS pass, whatever the AI decides. They test what
Python guarantees: cleaning, reconciliation, totals vs the clean data, and
that every number in the report comes from the Analyst. A failure means a
real bug: main.py then exits with an error code.

SOFT differences - reported, never failed. They compare the AI's judgement
calls with the answer key in data/README.md, and explain the effect.
"""

import json
from decimal import Decimal

import config
from tools import answer_key
from tools.csv_helpers import read_csv
from tools.review_checks import ReportReview


def money(text):
    return Decimal(text.replace(",", "").replace("+", ""))


class RunCheck:
    def __init__(self, output_dir=None, outcome=None, writer_runs=None):
        self.output_dir = config.OUTPUT_DIR if output_dir is None else output_dir
        self.outcome = outcome            # "delivered", "escalated" or None
        self.writer_runs = writer_runs
        self.hard = []   # {"check", "passed", "detail"}
        self.soft = []   # {"topic", "same", "detail"}

    def hard_check(self, check, passed, detail):
        self.hard.append({"check": check, "passed": bool(passed), "detail": detail})

    def soft_note(self, topic, same, detail):
        self.soft.append({"topic": topic, "same": bool(same), "detail": detail})

    def run(self):
        out = self.output_dir
        self.clean = read_csv(out / config.CLEAN_FILE_NAME)
        self.exceptions = read_csv(out / config.EXCEPTIONS_FILE_NAME)
        self.categorized = read_csv(out / config.CATEGORIZED_FILE_NAME)

        self.hard_checks()
        self.soft_checks()
        return {"hard_passed": all(c["passed"] for c in self.hard), "hard": self.hard, "soft": self.soft}

    # --- HARD -----------------------------------------------------------------

    def hard_checks(self):
        # 1. Cleaning: fully done by Python tools, so it must match the answer key exactly.
        duplicates = {int(r["source_line"]) for r in self.exceptions if r["issue"] == "duplicate"}
        missing = {int(r["source_line"]) for r in self.exceptions if r["issue"] == "missing amount"}
        raw = len(read_csv(config.TRANSACTIONS_FILE))
        self.hard_check(
            "Cleaning matches the answer key",
            raw == answer_key.RAW_ROWS and len(self.clean) == answer_key.CLEAN_ROWS
            and duplicates == set(answer_key.DUPLICATE_LINES) and missing == answer_key.MISSING_AMOUNT_LINES,
            f"{raw} raw rows, {len(self.clean)} clean, duplicates on lines {sorted(duplicates)}, "
            f"missing amounts on lines {sorted(missing)}")

        # 2. Every transaction has exactly one allowed category, with the right sign.
        problems = []
        for row in self.categorized:
            amount = Decimal(row["amount_czk"])
            if row["category"] not in config.CATEGORIES:
                problems.append(f"line {row['source_line']}: '{row['category']}'")
            elif (row["category"] == "Sales") != (amount > 0):
                problems.append(f"line {row['source_line']}: {row['category']} with amount {amount}")
        self.hard_check("Every transaction has exactly one valid category", not problems,
                        f"{len(self.categorized)} transactions" if not problems else "; ".join(problems))

        # 3. The AI may only decide the rows the keyword rules leave open.
        ai_lines = {int(r["source_line"]) for r in self.categorized if r["method"] == "AI"}
        self.hard_check("The AI only decided the unclear rows", ai_lines == set(answer_key.UNCLEAR_LINES),
                        f"AI decided lines {sorted(ai_lines)}; keyword rules decided the other "
                        f"{len(self.categorized) - len(ai_lines)}")

        # 4. Total expenses and sales don't depend on categories, so they must match the answer key.
        key = answer_key.read_totals_table()
        expenses = -sum(Decimal(r["amount_czk"]) for r in self.clean if Decimal(r["amount_czk"]) < 0)
        sales = sum(Decimal(r["amount_czk"]) for r in self.clean if Decimal(r["amount_czk"]) > 0)
        self.hard_check(
            "Total expenses and sales match the answer key",
            expenses == key["Total expenses"]["actual"] and sales == key["Sales (income)"]["actual"],
            f"total expenses {expenses:,.0f}, sales {sales:,.0f}")

        # 5-9. The Manager's reconciliation and number checks, run again independently.
        if not (self.output_dir / config.DRAFT_REPORT_FILE_NAME).exists():
            self.hard_check("Report checks", False, "No report was written")
            return
        review = ReportReview(output_dir=self.output_dir).run()
        checks = {c["check"]: c for c in review["checks"]}

        always_hard = ["Rows reconcile", "Totals reconcile"]
        report_hard = ["Budget table = Analyst's results", "Every number comes from the Analyst",
                       "Percentages belong to the right category"]
        for name in always_hard:
            self.hard_check(name, checks[name]["passed"], self.detail(checks[name], review))
        if self.outcome == "escalated":
            # The Manager refused to deliver this draft, so its failures are expected.
            for name in report_hard:
                self.soft_note(f"Last draft (not delivered): {name}", checks[name]["passed"],
                               self.detail(checks[name], review))
        else:
            for name in report_hard:
                self.hard_check(name, checks[name]["passed"], self.detail(checks[name], review))
        claims = checks["Every cause is supported by cited transactions"]
        self.soft_note("Claims supported by cited transactions", claims["passed"], self.detail(claims, review))

    def detail(self, check, review):
        if check["passed"]:
            return check["detail"]
        issues = [i["issue"] for i in review["issues"] if i["check"] == check["check"]]
        return check["detail"] + (": " + "; ".join(issues) if issues else "")

    # --- SOFT -----------------------------------------------------------------

    def soft_checks(self):
        # Outcome of the run.
        revisions = max(0, (self.writer_runs or 1) - 1)
        if self.outcome:
            self.soft_note("Outcome", self.outcome == "delivered",
                           f"{self.outcome}; Writer revisions needed: {revisions} of {config.MAX_REVISIONS}")
        else:
            self.soft_note("Outcome", False, "the Manager finished without delivering or escalating")

        # The AI's category decisions vs the answer key.
        rows = {int(r["source_line"]): r for r in self.categorized}
        for line, expected in answer_key.UNCLEAR_LINES.items():
            row = rows.get(line)
            if row is None:
                continue
            same = row["category"] == expected
            detail = (f"line {line} {row['description']}: AI chose {row['category']}"
                      + ("" if same else f", answer key says {expected}") + f" (reason: {row['reason']})")
            self.soft_note("AI category decision", same, detail)

        # Category totals vs the answer key (they differ only if the AI chose differently).
        key = answer_key.read_totals_table()
        totals = {}
        for row in self.categorized:
            totals[row["category"]] = totals.get(row["category"], Decimal(0)) + Decimal(row["amount_czk"])
        for category in config.CATEGORIES:
            if category == "Sales" or category not in key:
                continue
            actual = -totals.get(category, Decimal(0))
            expected = key[category]["actual"]
            if actual == expected:
                self.soft_note("Category total", True, f"{category} {actual:,.0f} = answer key")
            else:
                self.soft_note("Category total", False,
                               f"{category} {actual:,.0f} vs answer key {expected:,.0f} "
                               f"(difference {actual - expected:+,.0f}, caused by the AI decisions above)")

        # Flagged categories (they can change when category totals change).
        analysis_path = self.output_dir / config.ANALYSIS_FILE_NAME
        if analysis_path.exists():
            unusual = json.loads(analysis_path.read_text(encoding="utf-8"))["unusual_items"]
            over = [x["category"] for x in unusual["categories_over_budget"]]
            under = [x["category"] for x in unusual["categories_under_budget"]]
            self.soft_note("Over budget (>20%)", over == answer_key.OVER_BUDGET,
                           f"flagged {over or 'none'}; answer key {answer_key.OVER_BUDGET}")
            self.soft_note("Under budget (>20%)", under == answer_key.UNDER_BUDGET,
                           f"flagged {under or 'none'}; answer key {answer_key.UNDER_BUDGET}")

        # Rows the AI flagged for review: a judgement call, reported only.
        review_lines = [int(r["source_line"]) for r in self.categorized if r.get("needs_review") == "yes"]
        self.soft_note("Rows flagged needs_review", True,
                       f"lines {review_lines}" if review_lines else "none")


def format_run_check(result):
    lines = [f"# Run check – {config.REPORT_MONTH}", ""]
    status = "ALL PASSED" if result["hard_passed"] else "FAILED"
    lines += [f"## Hard checks (must always pass) – {status}", ""]
    for c in result["hard"]:
        lines.append(f"- [{'PASS' if c['passed'] else 'FAIL'}] {c['check']}: {c['detail']}")
    differences = [s for s in result["soft"] if not s["same"]]
    lines += ["", f"## Soft differences (reported, not failed) – {len(differences)} difference(s)", ""]
    for s in result["soft"]:
        lines.append(f"- [{'same' if s['same'] else 'DIFFERENT'}] {s['topic']}: {s['detail']}")
    return "\n".join(lines) + "\n"
