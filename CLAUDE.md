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
- Current stage: 2 (Agent engine) – built, waiting for Abanoub's go-ahead
- Test mode: without ANTHROPIC_API_KEY, agents use a scripted fake model
  (`agents/models.py`). Run tests with `python -m unittest -v`.
- Update this section after each finished stage.
