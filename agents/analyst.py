"""The Analyst (Reporting department): turns the categorized data into numbers."""

import config
from agents.base_agent import Agent
from tools.analyst_tools import ReportAnalyst, make_analyst_tools

INSTRUCTIONS = """You are the Analyst in the Reporting department of LedgerMind, a small \
accounting firm. Your job: produce the numbers for the monthly expense report.

Work only through your tools. You never calculate, round or estimate numbers yourself - \
the tools do all arithmetic.

Steps:
1. Load the month's data.
2. Calculate the totals per category.
3. Compare actual spend with budget.
4. Find unusual items.
5. Summarize the exceptions (probable duplicates, missing amounts, items needing review).
6. Save the analysis - it is the Writer's only source of numbers.

If a tool returns an error, read it, fix the cause and continue.
When done, reply with a short summary of the main findings, quoting numbers exactly as \
the tools returned them."""

# What the Analyst does in test mode (no API key).
FAKE_SCRIPT = [
    {"tool": "load_month_data"},
    {"tool": "calculate_totals"},
    {"tool": "compare_to_budget"},
    {"tool": "find_unusual_items"},
    {"tool": "summarize_exceptions"},
    {"tool": "save_analysis"},
    {"text": "(test mode) Analysis saved - see the tool results in the log."},
]


def task():
    return f"Analyse the categorized {config.month_name()} transactions against the budget."


def create_analyst(log, output_dir=None):
    analyst = ReportAnalyst(output_dir=output_dir)
    return Agent(
        name="Analyst",
        instructions=INSTRUCTIONS,
        tools=make_analyst_tools(analyst),
        log=log,
        fake_script=FAKE_SCRIPT,
    )
