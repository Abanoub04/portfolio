# LedgerMind – Project instructions for Claude Code

## What this project is
LedgerMind is a practice project for learning Python and AI agents.
It simulates a tiny accounting firm run only by AI agents. The firm takes a
month of business transactions and produces a monthly expense report.

The developer, Abanoub, is a beginner in Python and is learning by building
this project. He works in finance (controllership), so finance concepts are
familiar to him; Python and AI agents are new.

A visual overview of the whole project is in `docs/ledgermind-mindmap.html`.

## How we work (most important section)
This is a LEARNING project, not a speed project. Follow these rules:

1. Work on ONE task at a time. Only do the task Abanoub gives you.
   Do not build future stages or "helpful extras" in advance.
2. Before writing code, briefly explain your plan in simple English.
3. When Abanoub says he wants to try first, guide him with hints instead of
   writing the full solution.
4. Keep code simple and readable. Prefer clear beginner-friendly code over
   clever or compact code.
5. Add short comments explaining what each part does and why.
6. After finishing a task, give a short summary: which files changed,
   what the code does, and how to run it.
7. If something is unclear, ask one question instead of guessing.
8. Use only fake data. Never ask for or use real company data.
9. Never put API keys or passwords in code files. Use environment variables
   (from Stage 3 onward).

## The company (the agents)
- **Manager** – the only agent that talks to the user. Assigns work, passes
  results between departments, reviews the final report.
- **Bookkeeping department**
  - **Collector** – reads the transactions file and cleans it (fix dates,
    remove duplicates, flag missing amounts).
  - **Categorizer** – labels each transaction (Salaries, Rent, Travel,
    Software, Sales, Other...).
- **Reporting department**
  - **Analyst** – totals per category, comparison to budget, finds unusual costs.
  - **Writer** – turns the numbers into a short readable report.

Job flow: User → Manager → Collector → Categorizer → Manager → Analyst →
Writer → Manager (review) → User.

## Build stages
1. **Foundations** – toolbox lesson (calling functions by name), create fake
   `transactions.csv` and `budget.csv`.
2. **Rule-based employees** – each agent as plain Python with fixed rules,
   no AI. Manager runs them in order.
3. **AI brains** – connect to an AI model; give AI to Categorizer and Writer
   first, then Analyst.
4. **True agents** – each employee chooses its own tools in a loop; Manager
   delegates and reviews.
5. **Reliability** – verify totals against raw data, error handling, logging.

## Current status
- Current stage: 1 (Foundations)
- Current task: project setup
- Update this section when Abanoub says a task is finished.

## Technical choices
- Language: Python 3
- Stages 1–2: Python standard library only (e.g. `csv`, `datetime`).
  No pandas or other packages unless Abanoub asks.
- Stage 3+: packages will be added one at a time with explanation.
- Each agent lives in its own file in `agents/`.
- Tool functions live in `tools/`.
- Run everything from the project root with `python main.py`.

## Folder structure (target – create folders only when needed)
```
ledgermind/
├── CLAUDE.md
├── main.py              # starts the company
├── docs/                # mind map and notes
├── lessons/             # practice exercises (e.g. toolbox.py)
├── data/                # transactions.csv, budget.csv (fake data)
├── agents/              # manager.py, collector.py, categorizer.py, analyst.py, writer.py
├── tools/               # tool functions used by the agents
└── output/              # generated reports
```
