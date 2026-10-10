"""The Writer (Reporting department): writes the monthly report."""

from agents.base_agent import Agent
from tools.writer_tools import ReportWriter, make_writer_tools

INSTRUCTIONS = """You are the Writer in the Reporting department of LedgerMind, a small \
accounting firm. Your job: write the monthly expense report for the management of a small \
Czech design studio, in clear, plain business English.

Work only through your tools:
1. Read the analysis. It is your ONLY source of numbers.
2. Save the report with three text parts. The budget table and the lists of unusual items \
and exceptions are added automatically - do not repeat them in full.
   - summary: 3-5 sentences. Total expenses against budget, sales income, the result for \
the month, and the main concerns.
   - unusual_items_comment: 2-4 sentences explaining what drove each flagged item, using \
the largest items listed in the analysis.
   - exceptions_comment: 1-2 sentences on what must be followed up before the month is closed.

Number rules (strict):
- Copy every number exactly as it appears in the analysis, with the same formatting \
(e.g. 42,000 and +68.0%).
- Never calculate, add up, round or estimate a number. If a number you want is not in \
the analysis, describe it in words instead.
- save_report rejects any text containing a number that is not in the analysis. If that \
happens, fix the numbers it names and save again.

When done, reply with one sentence confirming the report was saved."""

# What the Writer does in test mode (no API key). The first save contains an
# invented, rounded number on purpose, to show the number check rejecting it.
FAKE_SUMMARY = (
    "Total expenses for September 2026 were 622,894 CZK against a budget of 605,000 CZK, "
    "which is +17,894 CZK (+3.0%) over budget. Sales income was 371,000 CZK, so the month "
    "closed with a result of -251,894 CZK. Spending was close to or below budget in most "
    "categories, but Travel (+70.3%) and Marketing (+68.0%) were well over budget."
)
FAKE_UNUSUAL = (
    "Both overspends are linked to the Design Days event in Berlin. Travel was driven by the "
    "Berlin hotel (9,200 CZK) and flights (7,800 CZK); Marketing by the conference booth "
    "(14,000 CZK) and Google Ads (12,000 CZK). No single expense outside Salaries and Rent "
    "exceeded 20,000 CZK."
)
FAKE_EXCEPTIONS = (
    "The 3 missing amounts must be obtained before the month can be closed, and the transfer "
    "on line 47 needs a supporting document."
)

FAKE_SCRIPT = [
    {"tool": "read_analysis"},
    {"tool": "save_report", "input": {
        "summary": "Total expenses were roughly 623,000 CZK.",
        "unusual_items_comment": FAKE_UNUSUAL,
        "exceptions_comment": FAKE_EXCEPTIONS}},
    {"tool": "save_report", "input": {
        "summary": FAKE_SUMMARY,
        "unusual_items_comment": FAKE_UNUSUAL,
        "exceptions_comment": FAKE_EXCEPTIONS}},
    {"text": "(test mode) Report saved."},
]

TASK = "Write the September 2026 monthly expense report."


def create_writer(log, output_dir=None):
    writer = ReportWriter(output_dir=output_dir)
    return Agent(
        name="Writer",
        instructions=INSTRUCTIONS,
        tools=make_writer_tools(writer),
        log=log,
        fake_script=FAKE_SCRIPT,
    )
