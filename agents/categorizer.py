"""The Categorizer (Bookkeeping department): gives every transaction one category."""

import config
from agents.base_agent import Agent
from agents.simulated_ai import CategorizerPolicy
from tools.categorizer_tools import TransactionCategorizer, make_categorizer_tools

INSTRUCTIONS = f"""You are the Categorizer in the Bookkeeping department of LedgerMind, \
a small accounting firm for a Czech design studio. Your job: give every clean transaction \
exactly one category.

Allowed categories (no others): {", ".join(config.CATEGORIES)}.
- Salaries: wages and the employer's social security and health insurance.
- Rent: office rent, service charges, rented parking spaces.
- Utilities: electricity, water, heating, internet, phone.
- Software: software subscriptions, hosting, domains, cloud services.
- Travel: transport, accommodation, fuel, parking while travelling.
- Marketing: advertising, printed promotion, events and trade fairs.
- Sales: income from customers (positive amounts only).
- Other: any other expense, including office running costs and professional fees.

Work only through your tools:
1. Load the clean data.
2. Apply the keyword rules. They handle the obvious rows.
3. For each row the rules left open, decide the category yourself and record it with \
set_category, giving a one-sentence reason a controller would accept. Use the description, \
counterparty and amount. If you are unsure (e.g. a transfer to a private person with no \
stated purpose), still choose the most likely category, but set needs_review to true and \
say in review_reason what a person should check.
4. Save the categorized data. Saving only works when every row has a category.

If a tool returns an error, read it, fix the cause and continue.
When done, reply with a short summary: transactions per category, which rows you \
categorized yourself and why, and which rows need review."""

# What the Categorizer does in test mode (no API key). In real mode the AI
# decides these three rows itself. The line numbers are the rows in
# data/transactions.csv that the keyword rules cannot decide.
FAKE_SCRIPT = [
    {"tool": "load_cleaned_data"},
    {"tool": "apply_keyword_rules"},
    {"tool": "set_category", "input": {"source_line": 29, "category": "Other",
        "reason": "Card payment at a supermarket (Albert) - small office purchase."}},
    {"tool": "set_category", "input": {"source_line": 43, "category": "Other",
        "reason": "Card payment at an electronics retailer (Alza) - small office equipment, "
                  "below the asset threshold, so expensed."}},
    {"tool": "set_category", "input": {"source_line": 47, "category": "Other",
        "reason": "Transfer to a private person; most likely a small service or expense refund.",
        "needs_review": True,
        "review_reason": "No stated purpose - confirm what the payment was for and get a document."}},
    {"tool": "save_categorized_data"},
    {"text": "(test mode) Categorizing finished - see save_categorized_data in the log for the counts."},
]


def task():
    return f"Categorize the clean {config.month_name()} transactions."


def create_categorizer(log, output_dir=None):
    categorizer = TransactionCategorizer(output_dir=output_dir)
    return Agent(
        name="Categorizer",
        instructions=INSTRUCTIONS,
        tools=make_categorizer_tools(categorizer),
        log=log,
        # September: the fixed demo script above. Other months: simulated AI.
        fake_script=FAKE_SCRIPT if config.REPORT_MONTH == "2026-09" else CategorizerPolicy(),
    )
