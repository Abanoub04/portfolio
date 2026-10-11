"""The Manager: the only agent that talks to the owner.

Runs Bookkeeping, then Reporting, reviews the report and either delivers it
or escalates to the owner.
"""

import config
from agents.base_agent import Agent
from agents.simulated_ai import ManagerPolicy
from agents.writer import create_writer
from tools.manager_tools import ManagerDesk, make_manager_tools

INSTRUCTIONS = f"""You are the Manager of LedgerMind, a small accounting firm run by AI agents. \
You are the only one who talks to the owner, Abanoub, a finance controller. You never \
calculate or write report content yourself - you delegate and you review.

How to handle a request for a monthly report:
1. Bookkeeping: ask_collector, then ask_categorizer.
2. Reporting: ask_analyst, then ask_writer.
3. review_report. It checks the reconciliation (rows and totals), data quality (every row \
in the report month, no possible duplicates left, no supplier money in Sales, every set-aside \
row in the report), the report's numbers against the Analyst's results, and that every \
stated cause is supported by cited transactions.
4. If the review passes: deliver_report with a short note to the owner on what was checked \
and anything they should follow up (missing amounts, items needing review).
5. If there are issues_for_writer: send the report back with ask_writer(feedback=...). \
The feedback must list each issue precisely, so the Writer can fix it. Then review again.
6. If there are data_issues (reconciliation or data quality), or the report still fails after {config.MAX_REVISIONS} \
revisions: do NOT deliver. escalate_to_owner with a summary and the full list of open issues.

Never deliver a report that has not passed review. When you finish, reply to the owner in \
2-4 sentences: delivered or escalated, and why."""

# Test mode (no API key): the first draft states a cause without citing
# transactions, so the review fails once; the revised draft passes.
FAKE_FEEDBACK = (
    "Unsupported claim in the unusual items comment: 'Both overspends are linked to the "
    "Design Days event in Berlin.' cites no transactions. Cite the source lines that prove "
    "it, or remove the claim."
)
FAKE_DELIVERY_NOTE = (
    "Checked before delivery: rows reconcile (raw = clean + probable duplicates + missing amounts), "
    "the sum of categories equals total expenses and matches the clean data, every number in "
    "the report matches the Analyst's results, and every stated cause is supported by cited "
    "transactions. One claim was sent back once for missing evidence and is now supported. "
    "To follow up: 3 missing amounts and 1 transfer needing review."
)

FAKE_SCRIPT = [
    {"tool": "ask_collector"},
    {"tool": "ask_categorizer"},
    {"tool": "ask_analyst"},
    {"tool": "ask_writer"},
    {"tool": "review_report"},
    {"tool": "ask_writer", "input": {"feedback": FAKE_FEEDBACK}},
    {"tool": "review_report"},
    {"tool": "deliver_report", "input": {"note": FAKE_DELIVERY_NOTE}},
    {"text": "(test mode) The September 2026 report is delivered. It passed review after one "
             "revision; see the review notes for what was checked."},
]


def task():
    return f"Prepare the {config.month_name()} report."


# The Manager needs more rounds than the other agents (it runs the whole job).
MAX_STEPS = 25


def create_manager(log, output_dir=None, writer_factory=create_writer, fake_script=None, collector_factory=None):
    desk = ManagerDesk(log, output_dir=output_dir, writer_factory=writer_factory,
                       collector_factory=collector_factory)
    agent = Agent(
        name="Manager",
        instructions=INSTRUCTIONS,
        tools=make_manager_tools(desk),
        log=log,
        # September: the fixed demo script above. Other months: simulated AI.
        fake_script=fake_script or (FAKE_SCRIPT if config.REPORT_MONTH == "2026-09" else ManagerPolicy()),
        max_steps=MAX_STEPS,
    )
    agent.desk = desk   # so tests and main.py can see what happened
    return agent
