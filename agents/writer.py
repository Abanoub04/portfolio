"""The Writer (Reporting department): writes the monthly report."""

import config
from agents.base_agent import Agent
from agents.simulated_ai import WriterPolicy
from tools.writer_tools import ReportWriter, make_writer_tools

INSTRUCTIONS = """You are the Writer in the Reporting department of LedgerMind, a small \
accounting firm. Your job: write the monthly expense report for the management of a small \
Czech design studio, in clear, plain business English.

Work only through your tools:
1. Read the analysis. It is your ONLY source of numbers.
2. Save the report with three text parts. The budget table and the lists of unusual items \
and exceptions are added automatically - do not repeat them in full.
   - summary: 3-5 sentences. Total expenses against budget and the main concerns. Do not \
state a result (sales minus expenses). Mention sales income only as a short side note at the end.
   - unusual_items_comment: 2-4 sentences explaining what drove each flagged item.
   - exceptions_comment: 1-2 sentences on what must be followed up before the month is closed.

Number rules (strict):
- Copy every number exactly as it appears in the analysis, with the same formatting \
(e.g. 42,000 and +68.0%).
- Never calculate, add up, round or estimate a number. If a number you want is not in \
the analysis, describe it in words instead.
- save_report rejects any text containing a number that is not in the analysis. If that \
happens, fix the numbers it names and save again.

Claim rules (strict):
- Every explanation of a cause ("driven by", "due to", "linked to", "because" ...) must \
cite the transactions that prove it by source line, e.g. "(line 38)" or "(lines 37, 38)". \
Use the source lines listed in the analysis.
- Only name things (places, events, suppliers) that appear in the cited transactions.
- If you cannot support a cause with specific transactions, do not state it.

When done, reply with one sentence confirming the report was saved."""

# --- Test mode (no API key) ---------------------------------------------------
# First draft: the first save contains an invented, rounded number on purpose
# (rejected by the number check). The saved draft then states a cause without
# citing any transaction ("linked to the Design Days event in Berlin"), which
# the Manager's review catches and sends back.
SUMMARY = (
    "Total expenses for September 2026 were 622,894 CZK against a budget of 605,000 CZK, "
    "which is +17,894 CZK (+3.0%) over budget. Travel (+70.3%) and Marketing (+68.0%) were "
    "well over budget. Software was -29.8% under budget, partly because the Figma "
    "subscription (line 8) has no amount yet. Side note: sales income was 371,000 CZK."
)
UNUSUAL_FIRST_DRAFT = (
    "Both overspends are linked to the Design Days event in Berlin. Travel was driven by the "
    "Berlin hotel (9,200 CZK, line 38) and flights (7,800 CZK, line 37); Marketing by the "
    "conference booth (14,000 CZK, line 40) and Google Ads (12,000 CZK, line 21). No single "
    "expense outside Salaries and Rent exceeded 20,000 CZK."
)
UNUSUAL_REVISED = (
    "Both overspends are linked to the Design Days event in Berlin (lines 37, 38, 40). "
    "Travel was driven by the Berlin hotel (9,200 CZK, line 38) and flights (7,800 CZK, "
    "line 37); Marketing by the Design Days conference booth (14,000 CZK, line 40) and "
    "Google Ads (12,000 CZK, line 21). No single expense outside Salaries and Rent "
    "exceeded 20,000 CZK."
)
EXCEPTIONS = (
    "The 3 missing amounts must be obtained before the month can be closed, and the transfer "
    "on line 47 needs a supporting document."
)

FAKE_SCRIPT_FIRST_DRAFT = [
    {"tool": "read_analysis"},
    {"tool": "save_report", "input": {
        "summary": "Total expenses were roughly 623,000 CZK.",
        "unusual_items_comment": UNUSUAL_FIRST_DRAFT,
        "exceptions_comment": EXCEPTIONS}},
    {"tool": "save_report", "input": {
        "summary": SUMMARY, "unusual_items_comment": UNUSUAL_FIRST_DRAFT, "exceptions_comment": EXCEPTIONS}},
    {"text": "(test mode) Draft report saved."},
]

FAKE_SCRIPT_REVISED = [
    {"tool": "read_analysis"},
    {"tool": "save_report", "input": {
        "summary": SUMMARY, "unusual_items_comment": UNUSUAL_REVISED, "exceptions_comment": EXCEPTIONS}},
    {"text": "(test mode) Revised report saved - every cause now cites its transactions."},
]


def task():
    return f"Write the {config.month_name()} monthly expense report."


def writer_task(feedback="", revision=0):
    """The task for the Writer, including the Manager's feedback on a revision."""
    if not feedback:
        return task()
    return (f"{task()}\n\nThis is revision {revision}. The Manager sent the report back "
            f"with this feedback:\n{feedback}")


def create_writer(log, output_dir=None, revision=0, fake_script=None):
    """revision 0 = first draft; 1, 2 = rewrites after the Manager's feedback."""
    if fake_script is None and config.REPORT_MONTH != "2026-09":
        fake_script = WriterPolicy()   # other months: simulated AI
    if fake_script is None:
        fake_script = FAKE_SCRIPT_FIRST_DRAFT if revision == 0 else FAKE_SCRIPT_REVISED

    writer = ReportWriter(output_dir=output_dir)
    return Agent(
        name="Writer",
        instructions=INSTRUCTIONS,
        tools=make_writer_tools(writer),
        log=log,
        fake_script=fake_script,
    )
