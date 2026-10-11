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
        key = answer_key.for_month()
        if key is None:
            self.soft_note("Answer key", False, f"no answer key for {config.REPORT_MONTH} - "
                                                f"comparisons with the key are skipped")

        # 1. Cleaning: fully done by Python tools, so it must match the answer key exactly.
        if key:
            found = {
                "raw rows": len(read_csv(config.TRANSACTIONS_FILE)),
                "clean rows": len(self.clean),
                "duplicates": sorted(int(r["source_line"]) for r in self.exceptions
                                     if r["issue"] in ("probable duplicate", "possible duplicate")),
                "missing amounts": sorted(int(r["source_line"]) for r in self.exceptions
                                          if r["issue"] == "missing amount"),
                "outside the period": sorted(int(r["source_line"]) for r in self.exceptions
                                             if r["issue"] == "outside the period"),
            }
            expected = {
                "raw rows": key["raw_rows"],
                "clean rows": key["clean_rows"],
                "duplicates": sorted(key["duplicates"]),
                "missing amounts": sorted(key["missing_amounts"]),
                "outside the period": sorted(key["outside_period"]),
            }
            wrong = [f"{name}: expected {expected[name]}, found {found[name]}"
                     for name in expected if found[name] != expected[name]]
            self.hard_check("Cleaning matches the answer key", not wrong,
                            "; ".join(f"{name} {value}" for name, value in found.items()) if not wrong
                            else "; ".join(wrong))

        # 2. Every transaction has exactly one allowed category, with the right sign:
        #    Sales positive; expenses negative, or positive only as a refund flagged for review.
        problems = []
        for row in self.categorized:
            amount = Decimal(row["amount_czk"])
            if row["category"] not in config.CATEGORIES:
                problems.append(f"line {row['source_line']}: '{row['category']}'")
            elif row["category"] == "Sales" and amount <= 0:
                problems.append(f"line {row['source_line']}: Sales with amount {amount}")
            elif row["category"] != "Sales" and amount > 0 and row.get("needs_review") != "yes":
                problems.append(f"line {row['source_line']}: refund in {row['category']} not flagged for review")
        self.hard_check("Every transaction has exactly one valid category", not problems,
                        f"{len(self.categorized)} transactions" if not problems else "; ".join(problems))

        # 3. The AI may only decide the rows the keyword rules leave open.
        ai_lines = {int(r["source_line"]) for r in self.categorized if r["method"] == "AI"}
        if key:
            self.hard_check("The AI only decided the unclear rows", ai_lines == set(key["unclear_lines"]),
                            f"AI decided lines {sorted(ai_lines)} (answer key: {sorted(key['unclear_lines'])}); "
                            f"keyword rules decided the other {len(self.categorized) - len(ai_lines)}")

        # 4. Total expenses and sales. Which expense category a row is in doesn't
        #    matter here; only Sales vs expenses does - and the code decides that
        #    (customer income is Sales, a supplier's refund is not).
        if key:
            table = answer_key.read_totals_table()
            sales = sum(Decimal(r["amount_czk"]) for r in self.categorized if r["category"] == "Sales")
            expenses = -sum(Decimal(r["amount_czk"]) for r in self.categorized if r["category"] != "Sales")
            expected_expenses = table["Total expenses"]["actual"]
            expected_sales = table["Sales (income)"]["actual"]
            passed = expenses == expected_expenses and sales == expected_sales
            detail = f"total expenses {expenses:,.0f}, sales {sales:,.0f}"
            if not passed:
                detail = (f"total expenses {expenses:,.0f} vs answer key {expected_expenses:,.0f} "
                          f"(difference {expenses - expected_expenses:+,.0f}); sales {sales:,.0f} vs "
                          f"answer key {expected_sales:,.0f} (difference {sales - expected_sales:+,.0f})")
            self.hard_check("Total expenses and sales match the answer key", passed, detail)

        # 5-9. The Manager's reconciliation and number checks, run again independently.
        if not (self.output_dir / config.DRAFT_REPORT_FILE_NAME).exists():
            self.hard_check("Report checks", False, "No report was written")
            return
        review = ReportReview(output_dir=self.output_dir).run()
        checks = {c["check"]: c for c in review["checks"]}

        always_hard = ["Rows reconcile", "Totals reconcile",
                       "Every clean row is dated in the report month",
                       "No possible duplicates left in the clean data",
                       "No supplier money counted as Sales",
                       "Every set-aside row appears in the report"]
        report_hard = ["Budget table = Analyst's results", "Every number comes from the Analyst",
                       "Percentages belong to the right category", "No signed amounts with over/under budget",
                       "Deliverables are present and up to date",
                       "Deliverables match the Analyst's results"]
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

        # Rows the AI flagged for review: a judgement call, reported only.
        review_lines = [int(r["source_line"]) for r in self.categorized if r.get("needs_review") == "yes"]
        self.soft_note("Rows flagged needs_review", True,
                       f"lines {review_lines}" if review_lines else "none")

        key = answer_key.for_month()
        if key is None:
            return

        # The AI's category decisions vs the answer key.
        rows = {int(r["source_line"]): r for r in self.categorized}
        for line, expected in key["unclear_lines"].items():
            row = rows.get(line)
            if row is None:
                continue
            same = row["category"] == expected
            detail = (f"line {line} {row['description']}: AI chose {row['category']}"
                      + ("" if same else f", answer key says {expected}") + f" (reason: {row['reason']})")
            self.soft_note("AI category decision", same, detail)

        # Refunds: must sit in the expense category they refund.
        for line, expected in key.get("refunds", {}).items():
            row = rows.get(line)
            if row is not None:
                self.soft_note("Refund", row["category"] == expected,
                               f"line {line} {row['description']}: in {row['category']}"
                               + ("" if row["category"] == expected else f", answer key says {expected}"))

        # Category totals vs the answer key. They differ when the AI chose a
        # different category, or when the cleaning differs from the key.
        table = answer_key.read_totals_table()
        totals = {}
        for row in self.categorized:
            totals[row["category"]] = totals.get(row["category"], Decimal(0)) + Decimal(row["amount_czk"])
        for category in config.CATEGORIES:
            if category == "Sales" or category not in table:
                continue
            actual = -totals.get(category, Decimal(0))
            expected = table[category]["actual"]
            if actual == expected:
                self.soft_note("Category total", True, f"{category} {actual:,.0f} = answer key")
            else:
                self.soft_note("Category total", False,
                               f"{category} {actual:,.0f} vs answer key {expected:,.0f} "
                               f"(difference {actual - expected:+,.0f}; see the cleaning and AI decisions above)")

        # Flagged categories (they can change when category totals change).
        analysis_path = self.output_dir / config.ANALYSIS_FILE_NAME
        if analysis_path.exists():
            unusual = json.loads(analysis_path.read_text(encoding="utf-8"))["unusual_items"]
            over = [x["category"] for x in unusual["categories_over_budget"]]
            under = [x["category"] for x in unusual["categories_under_budget"]]
            self.soft_note("Over budget (>20%)", over == key["over_budget"],
                           f"flagged {over or 'none'}; answer key {key['over_budget'] or 'none'}")
            self.soft_note("Under budget (>20%)", under == key["under_budget"],
                           f"flagged {under or 'none'}; answer key {key['under_budget'] or 'none'}")



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
