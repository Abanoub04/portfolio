"""Simulated AI for test mode, used for every month except September.

September's test mode uses fixed scripts with deliberate mistakes (see the
agent files). Those scripts refer to September's line numbers, so they
can't be used for another month. For other months, these small rule-based
"policies" stand in for the AI: they read the tool results and decide the
next step, like the real model would - but with simple, predictable rules.

They are NOT the real AI. With an API key, Claude makes these decisions
itself and may decide differently (often better). They exist so that the
whole company - and especially the parts that don't depend on the AI - can
be tested on new data without an API key.
"""

import json
from decimal import Decimal

import config


def last_tool_result(messages):
    """The latest tool result in the conversation: (data, is_error).
    data is the parsed JSON when possible, otherwise the text."""
    for message in reversed(messages):
        if message["role"] == "user" and isinstance(message["content"], list):
            result = message["content"][-1]
            try:
                data = json.loads(result["content"])
            except (ValueError, TypeError):
                data = result["content"]
            return data, bool(result.get("is_error"))
    return None, False


def count(number, singular, plural):
    """count(1, "row", "rows") -> "1 row"; count(3, ...) -> "3 rows"."""
    return f"{number} {singular if number == 1 else plural}"


def tool(name, **inputs):
    return {"tool": name, "input": inputs}


class CategorizerPolicy:
    """Loads the data, applies the keyword rules, then decides each open row:
    - no keyword, positive amount: try Sales (customer income); if the tool
      refuses because it comes from a supplier, book it as a refund in Other
    - no keyword, negative amount: Other
    - several keywords matched: the first one
    - any other case: Other
    Every row it decides is flagged for review."""

    def __init__(self):
        self.stage = "load"
        self.rows = []         # rows still to decide: list of lists of attempts
        self.attempts = []     # remaining attempts for the current row

    def __call__(self, messages):
        result, is_error = last_tool_result(messages)

        if self.stage == "load":
            self.stage = "keywords"
            return tool("load_cleaned_data")
        if self.stage == "keywords":
            self.stage = "decide"
            return tool("apply_keyword_rules")
        if self.stage == "decide":
            if isinstance(result, dict) and "left_for_you_to_decide" in result:
                self.rows = [self.plan(row) for row in result["left_for_you_to_decide"]]
            if is_error and self.attempts:
                return self.attempts.pop(0)      # the last try was refused: next option
            if self.rows:
                self.attempts = self.rows.pop(0)
                return self.attempts.pop(0)
            self.stage = "save"
            return tool("save_categorized_data")
        return {"text": "(test mode, simulated AI) Categorizing finished; uncertain rows are flagged for review."
                if not is_error else f"(test mode, simulated AI) Could not save: {result}"}

    def plan(self, row):
        line = row["source_line"]
        positive = Decimal(row["amount_czk"]) > 0
        why = row["why_unclear"]
        unknown = f"Unknown supplier ({row['counterparty']}) - confirm the category."

        if why == "no keyword matched" and positive:
            return [
                tool("set_category", source_line=line, category="Sales",
                     reason="Positive amount with no keyword rule - looks like customer income.",
                     needs_review=True, review_reason="Not recognised as an invoice - confirm it is income."),
                tool("set_category", source_line=line, category="Other",
                     reason="Positive amount from a supplier - a refund.",
                     needs_review=True, review_reason=unknown),
            ]
        if why.startswith("keywords for several"):
            first = why.split("[")[1].split(",")[0].strip("'] ")
            return [tool("set_category", source_line=line, category=first,
                         reason=f"Several keyword rules matched; {first} looks most likely.",
                         needs_review=True, review_reason="Several categories possible - confirm.")]
        return [tool("set_category", source_line=line, category="Other",
                     reason="Supplier not known to the keyword rules.",
                     needs_review=True, review_reason=unknown)]


class WriterPolicy:
    """Reads the analysis and writes a plain report from it: every number is
    copied from the analysis, and every cause cites the transactions behind it."""

    def __init__(self):
        self.stage = "read"

    def __call__(self, messages):
        result, is_error = last_tool_result(messages)
        if self.stage == "read":
            self.stage = "write"
            return tool("read_analysis")
        if self.stage == "write":
            self.stage = "files"
            return tool("save_report", **self.texts(result))
        if self.stage == "files" and not is_error:
            self.stage = "done"
            return tool("create_deliverables")
        if is_error:
            return {"text": f"(test mode, simulated AI) Stopped: {result}"}
        return {"text": "(test mode, simulated AI) Draft report and files saved."}

    def texts(self, analysis):
        budget = analysis["budget_vs_actual"]
        total = budget["total"]
        unusual = analysis["unusual_items"]
        exceptions = analysis["exceptions"]

        summary = [f"Total expenses for {config.month_name()} were {total['actual_czk']} CZK against a budget "
                   f"of {total['budget_czk']} CZK: {total['variance_phrase']}."]
        over = unusual["categories_over_budget"]
        under = unusual["categories_under_budget"]
        threshold = unusual["over_budget_threshold"]
        if over:
            summary.append(f"More than {threshold} over budget: "
                           + ", ".join(f"{x['category']} ({x['variance_percent'].lstrip('+')})" for x in over) + ".")
        else:
            summary.append(f"No category was more than {threshold} over budget.")
        if under:
            summary.append(f"More than {threshold} under budget, which may indicate missing or late costs: "
                           + ", ".join(f"{x['category']} ({x['variance_percent'].lstrip('-')})" for x in under) + ".")
        summary.append(f"Side note: sales income was {analysis['totals']['sales_income_czk']} CZK.")

        comments = []
        for item in over:
            largest = item.get("largest_items", [])[:2]
            if largest:
                parts = [f"{x['description']} ({x['amount_czk']} CZK, line {x['source_line']})" for x in largest]
                comments.append(f"{item['category']} was driven mainly by {' and '.join(parts)}.")
        if not over:
            comments.append("There were no overspends to explain.")
        if not unusual["large_transactions"]:
            comments.append(f"No single expense outside {' and '.join(unusual['large_transactions_excluding'])} "
                            f"exceeded {unusual['large_transaction_threshold_czk']} CZK.")

        follow_up = []
        if exceptions["probable_duplicates_count"]:
            follow_up.append(f"confirm {count(exceptions['probable_duplicates_count'], 'probable duplicate', 'probable duplicates')} "
                             f"against the bank statement")
        if exceptions["possible_duplicates_count"]:
            follow_up.append(f"confirm {count(exceptions['possible_duplicates_count'], 'possible duplicate', 'possible duplicates')} "
                             f"against the bank statement")
        if exceptions["outside_the_period_count"]:
            follow_up.append(f"book {count(exceptions['outside_the_period_count'], 'row', 'rows')} from another "
                             f"period in its own month")
        if exceptions["missing_amounts_count"]:
            follow_up.append(f"obtain {count(exceptions['missing_amounts_count'], 'missing amount', 'missing amounts')}")
        if exceptions["needs_review_count"]:
            follow_up.append(f"check {count(exceptions['needs_review_count'], 'item', 'items')} needing review")
        exceptions_comment = ("Before the month is closed: " + ", ".join(follow_up) + "."
                              if follow_up else "No exceptions need follow-up.")

        return {"summary": " ".join(summary), "unusual_items_comment": " ".join(comments),
                "exceptions_comment": exceptions_comment}


class ManagerPolicy:
    """Runs the departments, reviews, sends the report back with the review's
    issues (at most config.MAX_REVISIONS times), then delivers or escalates."""

    def __init__(self):
        self.queue = [tool("ask_collector"), tool("ask_categorizer"), tool("ask_analyst"),
                      tool("ask_writer"), tool("review_report")]
        self.last_tool = None
        self.finished = None

    def __call__(self, messages):
        result, is_error = last_tool_result(messages)

        if self.finished:
            return {"text": self.finished}

        if is_error and self.last_tool in ("ask_collector", "ask_categorizer", "ask_analyst", "ask_writer",
                                           "deliver_report"):
            return self.send(tool("escalate_to_owner",
                                  summary=f"{self.last_tool} failed, so the report could not be prepared.",
                                  issues=[str(result)]))

        if self.last_tool == "review_report" and isinstance(result, dict):
            if result["passed"]:
                note = ("Checked before delivery: " + "; ".join(result["checks"]) +
                        ". Please look at the exceptions section (probable duplicates, missing amounts, "
                        "items needing review) before closing the month.")
                return self.send(tool("deliver_report", note=note))
            if result["data_issues"] or result["revisions_left"] == 0:
                return self.send(tool("escalate_to_owner",
                                      summary="The report does not pass review and cannot be delivered.",
                                      issues=result["data_issues"] + result["issues_for_writer"]))
            feedback = "Fix these issues:\n" + "\n".join(f"- {issue}" for issue in result["issues_for_writer"])
            self.queue = [tool("ask_writer", feedback=feedback), tool("review_report")]

        if self.last_tool in ("deliver_report", "escalate_to_owner"):
            outcome = "delivered" if self.last_tool == "deliver_report" else "escalated to the owner"
            self.finished = f"(test mode, simulated AI) The {config.month_name()} report was {outcome}."
            return {"text": self.finished}

        if not self.queue:
            return {"text": "(test mode, simulated AI) Stopped: nothing left to do."}
        return self.send(self.queue.pop(0))

    def send(self, step):
        self.last_tool = step["tool"]
        return step
