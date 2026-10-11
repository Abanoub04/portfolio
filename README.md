# LedgerMind

A small accounting firm run entirely by AI agents. It takes one month of
(fake) business transactions and delivers a monthly expense report.

- **Manager** – talks to you, delegates, reviews the report, delivers or escalates
- **Bookkeeping** – Collector (cleans the data), Categorizer (assigns categories)
- **Reporting** – Analyst (all calculations), Writer (writes the report)

All numbers are calculated by Python tools, never by the AI. See `CLAUDE.md`
for the full brief and `docs/ledgermind-mindmap.html` for an overview.

## Run it on your own computer

You need **Python 3.10 or newer** and **git**. Check with `python --version`
(on macOS/Linux it may be `python3`).

### 1. Clone the project

```
git clone https://github.com/Abanoub04/portfolio.git
cd portfolio
```

### 2. Create a virtual environment and install

A virtual environment keeps this project's packages separate from the rest
of your computer.

macOS / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Check that everything works – free, no key needed

```
python -m unittest
```

All tests should pass (`OK`). The tests always use a fake model, even after
you add your key, so they never cost anything.

You can also run the whole company in test mode:
```
python main.py
```

### 4. Add your API key

Get a key at https://platform.claude.com (API keys). Then copy the template:

macOS / Linux: `cp .env.example .env`
Windows: `copy .env.example .env`

Open `.env` in a text editor and replace `your-key-here` with your key:
```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is listed in `.gitignore`, so your key is never committed. Never put
the key in any other file.

### 5. Run it for real

```
python main.py
```

The first line should say `Mode: REAL model claude-opus-5-5`. A run takes a
few minutes and costs roughly **$1** (see below).

### 6. Read the results (in `output/`)

| File | What it is |
|---|---|
| `report_2026-09.md` | The delivered report (only if the Manager's review passed) |
| `report_2026-09.xlsx` | Excel: Summary (actual = SUMIFS over whole Transactions columns, so added rows count; variance and variance % as formulas), Transactions, Exceptions; prints landscape, one page wide |
| `report_2026-09.docx` | Word: the same report as a formatted document |
| `report_2026-09.pptx` | PowerPoint: 4-slide management deck with action titles – headline numbers, budget vs actual, unusual items (refunds named in their category), actions before closing |
| `review_notes_2026-09.md` | What the Manager checked, round by round |
| `escalation_2026-09.md` | Only if the Manager refused to deliver – the open issues |
| `run_check_2026-09.md` | Hard checks and soft differences from the answer key (below) |
| `exceptions_2026-09.csv` | Probable duplicates and missing amounts that were set aside |
| `transactions_categorized_2026-09.csv` | Every transaction with its category and reason |

All file names contain the month, so different months never overwrite each other.

The full log of who did what is in `logs/`.

## Deliverable files

The Writer's `create_deliverables` tool builds the Excel, Word and PowerPoint
files with Python from the Analyst's results and the Writer's checked text -
the AI never types a number into a file. Before delivery the Manager opens
each file again, reads the numbers back and compares them with the Analyst's
results (Excel formulas are checked to be the expected formulas, and their
results worked out from the rows in the Transactions sheet). Any mismatch
blocks delivery. The files keep `draft_` names until the review passes.

Variances are written without signs in sentences: "CZK 33,514 (5.5%) under
budget", never "CZK -33,514 under budget". The Writer's save and the
Manager's review both block signed "over/under budget" phrases in every format.

## Options

```
python main.py                    # September 2026 (real model if a key is set)
python main.py --test             # force test mode (fake model), even with a key in .env
python main.py --month 2026-10    # another month: reads data/transactions_2026-10.csv
python main.py --test --month 2026-10
```

## Test months

| Month | File | Answer key | What it tests |
|---|---|---|---|
| September 2026 | `data/transactions.csv` | `data/README.md` | mixed date formats, exact duplicates, missing amounts, unclear rows |
| October 2026 | `data/transactions_2026-10.csv` | `data/answer_key_2026-10.md` | a reworded duplicate, a row from the wrong month, a refund, a supplier no keyword rule knows |

In test mode, September uses fixed scripts with deliberate mistakes (to show
the Manager's review working). Other months use a simple simulated AI
(`agents/simulated_ai.py`), which follows fixed rules - the real model
decides for itself and may decide better.

Both months pass every hard check in test mode. October's only soft
difference is the simulated AI booking the new supplier (Taskly) in Other
instead of Software.

## How the data is cleaned

- **Probable duplicates:** identical rows. **Possible duplicates:** same
  counterparty and amount within 3 days, even if worded differently. Both
  are excluded from the totals and always listed in the report, to be
  confirmed against the bank statement.
- **Outside the period:** rows dated outside the report month are set aside
  and listed (cut-off).
- **Refunds:** a positive amount from a supplier reduces its expense
  category and is flagged for review. Only customer income goes to Sales.
- **Missing amounts:** set aside, never guessed.

Before delivering, the Manager also runs data-quality checks that need no
answer key, so they work on a real client file: every clean row is in the
report month, no possible duplicates are left, no supplier money is in Sales,
and every set-aside row appears in the report. If any fails, the report is
not delivered: the Manager escalates.

## Hard checks and soft differences

With the real model, the AI's choices can differ from run to run. After
every run, `main.py` writes `output/run_check_2026-09.md` with two parts:

**Hard checks – must always pass.** These test what Python guarantees,
whatever the AI decides: cleaning matches the answer key (61 rows,
54 clean, duplicates and missing amounts on the right lines), every
transaction has exactly one valid category, the AI only decided the
3 unclear rows, rows and totals reconcile with the clean data, total
expenses (622,894) and sales (371,000) match, and every number in the
report comes from the Analyst. If one fails, it is a bug: `main.py` says
so and exits with an error code.

**Soft differences – reported, never failed.** These are the AI's
judgement calls compared with the answer key in `data/README.md`: the
category it chose for the ALBERT, ALZA and transfer rows, the category
totals that change as a result, which categories get flagged over or under
budget, which rows it marked for review, how many revisions the Writer
needed, and whether the report was delivered or escalated.

Example: if the AI puts the ALZA payment (4,390 CZK) in Software instead of
Other, the run check shows Software +4,390 and Other −4,390 against the
answer key, and Software is no longer flagged as under budget. The hard
checks still pass, because the totals still reconcile.

## Cost

Model: `claude-opus-5-5` at $4 per million input tokens and $20 per million
output tokens (thinking counts as output). One full run makes about 35–45
model calls across the five agents. Measured from the test-mode run, they
send about 55,000 tokens of input; a real run adds the AI's own thinking
and text. Estimate for one run: **about $1, typically $0.75–$2**. A run
where the Writer needs two revisions costs more than one that passes first
time.

To spend less, change `MODEL` in `config.py` to `claude-sonnet-5-5`
(about half the price). Check actual usage in the Claude Console.

## Common problems

| Message | What to do |
|---|---|
| `Mode: TEST` although you added a key | The `.env` file must be in the project folder, next to `main.py` |
| `still contains the placeholder` | Replace `your-key-here` in `.env` with your real key |
| `The API key was rejected` | Copy the key again – no spaces or quotes around it |
| `Rate limit or credit limit reached` | Wait a minute, or add credit in the Console |
| `Could not reach the API` | Check your internet connection or proxy |
