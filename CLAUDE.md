# LedgerMind – Build brief for Claude Code

## What we are building
LedgerMind is a small company run entirely by AI agents. It works as a
mini accounting firm: it receives one month of business transactions and
delivers a monthly expense report.

The owner, Abanoub, directs the project and plans it in a separate chat.
You (Claude Code) do the building. Abanoub works in finance
(controllership), so the accounting logic should make sense to a
professional.

A visual overview of the company is in `docs/ledgermind-mindmap.html`.

## The company
Five AI agents, each with its own role, instructions and tools.

- **Manager** – the only agent that talks to the user. Receives the job,
  delegates to the two departments, passes results between them, reviews
  the final report and sends it back if something is wrong.
- **Bookkeeping department**
  - **Collector** – reads the raw transactions file and cleans it: fixes
    date formats, removes duplicates, flags rows with missing amounts.
  - **Categorizer** – assigns each transaction a category (Salaries, Rent,
    Travel, Software, Marketing, Utilities, Sales, Other).
- **Reporting department**
  - **Analyst** – totals per category, comparison with budget, flags
    unusual items (e.g. a category more than 20% over budget).
  - **Writer** – writes the final report in clear business English.

Job flow: User → Manager → Collector → Categorizer → Manager → Analyst →
Writer → Manager (review) → User.

## Design rules
1. Every agent is a real AI agent: an AI model + its own tools + a loop
   (decide → use tool → read result → repeat until done).
2. Agents can only act through their tools. Tools are normal Python
   functions.
3. **All calculations are done by Python tools, never by the AI model
   itself.** The model decides what to calculate; the tool calculates.
   This keeps the numbers correct.
4. The Manager delegates through tools (e.g. `ask_collector`,
   `ask_analyst`). Each department agent is called like a tool.
5. Every agent action is written to a log, so we can see who did what.
6. The Manager must verify the final totals against the cleaned data
   before delivering the report.
7. Only fake data. No real company data.
8. The API key is read from the environment variable `ANTHROPIC_API_KEY`.
   Never write keys into files.

## Technical choices
- Python 3, Anthropic Python SDK (`anthropic`) with tool use.
- Model name stored in one place (`config.py`) so it is easy to change.
- Each agent in its own file in `agents/`; shared agent loop in
  `agents/base_agent.py`.
- Tool functions in `tools/`.
- Run the whole company with `python main.py`.

## Folder structure
```
ledgermind/
├── CLAUDE.md
├── config.py            # model name, settings
├── main.py              # starts the company
├── docs/                # mind map
├── data/                # transactions.csv, budget.csv (fake)
├── agents/              # base_agent.py, manager.py, collector.py,
│                        # categorizer.py, analyst.py, writer.py
├── tools/               # tool functions per department
├── logs/                # action logs per run
└── output/              # finished reports
```

## Build stages
1. **Setup and data** – folders, config, requirements, fake data with
   realistic messiness (duplicates, mixed date formats, missing amounts).
2. **Agent engine** – the shared agent loop in `base_agent.py` + logging.
3. **Bookkeeping department** – Collector and Categorizer with tools.
4. **Reporting department** – Analyst and Writer with tools.
5. **Manager** – delegation, review, and verification of totals.
6. **Full run** – `python main.py` produces a report end to end.

## How to work
- Build one stage at a time. After each stage, stop, summarize what was
  built and how to test it, and wait for Abanoub's go-ahead.
- Test each stage before reporting it as done.
- If a decision is unclear, ask one question.

## Current status
- Stage 1 (Setup and data) – done
- Stage 2 (Agent engine) – done
- Stage 3 (Bookkeeping department) – done
- Stage 4 (Reporting department) – done
- Stage 5 (Manager) – done
- Stage 6 (Full run) – done: first real run on Abanoub's computer passed all
  hard checks, delivered first time, cost about $0.34
- Follow-ups after the real run (PR #6, first round): probable-duplicate labels,
  --test / --month switches, October 2026 test month, simulated AI for months
  other than September (agents/simulated_ai.py)
- October gaps fixed (PR #6) – done; real October run: 13/13 hard, 0 soft
  - Collector: possible duplicates (same counterparty + amount within
    DUPLICATE_WINDOW_DAYS, any wording) and cut-off (rows outside the report
    month) are set aside and always listed in the report
  - Categorizer: a positive amount from a supplier is a refund (reduces its
    expense category, flagged for review); Sales is customer income only
  - Manager data-quality checks without an answer key (tools/review_checks.py,
    rules in tools/data_rules.py): rows in the report month, no possible
    duplicates, no supplier money in Sales, every set-aside row in the report.
    A failure is a data issue: delivery is blocked, the Manager escalates.
- Deliverable files (PR #7) – done
  - Writer tool create_deliverables builds draft_report_YYYY-MM.xlsx/.docx/.pptx
    with Python (tools/excel_report.py, word_report.py, slides_report.py) from
    the analysis and the saved draft text; Markdown and Word share one content
    model (tools/report_content.py)
  - Manager review reads every file back (tools/deliverable_checks.py); a
    missing/out-of-date file goes back to the Writer, a wrong number is a data
    issue (no delivery, escalate). deliver_report copies the files to report_*.
  - Both test months: 15/15 hard checks, files delivered
- Deliverable polish (PR #8) – done
  - Excel Summary actual = -SUMIFS over Transactions (refunds net automatically);
    Manager checks each formula and works out its result from the Transactions rows.
    Print setup: landscape, one page wide, header row repeated.
  - No double negatives: the Analyst gives variance_phrase ("CZK 33,514 (5.5%)
    under budget"); save_report and the Manager's review block signed
    "over/under budget" phrases (md, Word, PowerPoint).
  - PowerPoint: action titles built by Python from the analysis, no explanation
    subtitle, slide 4 two panels (excluded / included-to-review), larger text.
  - Word tables: a text column is never narrower than its longest word.
  - Both test months: 16/16 hard checks
- Current: final polish – built, waiting for Abanoub's go-ahead
  - Slide 1: headline cards + the to-do line only (category detail is on slide 3)
  - Slide 3: a refund is mentioned in its category's line ("CZK 3,100 of the gap
    is a refund (line 25)"); the Analyst lists refunds per category in totals
  - Slide 4: panels start right under the title
  - Excel SUMIFS over whole columns (Transactions!$E:$E, $F:$F), so added rows
    count; the Manager's check works out the result from every row in the sheet
  - Both test months: 16/16 hard checks
- API key: ANTHROPIC_API_KEY from the environment or a .env file (config.py
  loads it; .env is gitignored; .env.example is the template). The test
  suite forces test mode (tests/__init__.py), so tests never call the API.
- After each run main.py writes output/run_check_YYYY-MM.md: HARD checks
  (must pass, exit code 1 if not) and SOFT differences vs the answer key
  (tools/run_checks.py, answer key in tools/answer_key.py).
- Generated (not committed) in output/, all named with the month:
  transactions_clean_YYYY-MM.csv, exceptions_YYYY-MM.csv,
  transactions_categorized_YYYY-MM.csv, analysis_YYYY-MM.json (Analyst),
  draft_report_YYYY-MM.md (Writer), report_YYYY-MM.md (only after the
  Manager's review passed), review_notes_YYYY-MM.md, escalation_YYYY-MM.md
  (only if not delivered)
- Manager review checks are in tools/review_checks.py (plain Python). The
  Writer may be sent back at most MAX_REVISIONS (2) times, then the Manager
  must escalate; both rules are enforced in tools/manager_tools.py.
- Writer number check: save_report rejects text containing any number that
  is not in the Analyst's analysis file.
- Test mode: without ANTHROPIC_API_KEY, agents use a scripted fake model
  (`agents/models.py`). Run tests with `python -m unittest -v`.
- Update this section after each finished stage.
