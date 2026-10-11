"""The Collector's tools: read the raw transactions file and clean it.

All the actual work happens here, in plain Python. The Collector (the AI)
only decides which tool to use and when.

Two rules are enforced by the code itself, whatever the AI decides:
  - Nothing is deleted silently. Every row that leaves the clean data
    goes to the exceptions list with a reason.
  - Nothing is guessed. A missing amount or an unreadable date is set
    aside, never filled in.
  - Nothing from another month is counted. Rows dated outside the report
    month are set aside as "outside the period" (cut-off).

Every row keeps its line number from the original file ("source_line"),
so each clean row and each exception can be traced back to the source.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import config
from tools.csv_helpers import read_csv, write_csv
from tools.data_rules import days_between, in_report_month, possible_duplicate_pairs

CLEAN_COLUMNS = ["source_line", "date", "description", "counterparty", "amount_czk"]
EXCEPTION_COLUMNS = ["source_line", "date", "description", "counterparty", "amount_czk", "issue", "detail"]


class TransactionCleaner:
    """Holds the transactions in memory while the Collector works on them."""

    def __init__(self, source_file=None, output_dir=None):
        self.source_file = Path(source_file or config.TRANSACTIONS_FILE)
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)

        self.rows = []         # rows still in the clean data
        self.exceptions = []   # rows set aside, each with an issue and detail
        self.rows_loaded = 0

        # Which cleaning steps have been done. save_cleaned_data() checks
        # these, so a half-cleaned file can never be saved.
        self.done = {"load": False, "dates": False, "period": False, "amounts": False, "duplicates": False}

    # --- helpers ----------------------------------------------------------

    def set_aside(self, row, issue, detail):
        """Move a row from the clean data to the exceptions list."""
        exception = dict(row)
        exception["issue"] = issue
        exception["detail"] = detail
        self.exceptions.append(exception)

    def require(self, step, message):
        """Stop with a clear error if an earlier step has not been done."""
        if not self.done[step]:
            raise RuntimeError(message)

    # --- tools ------------------------------------------------------------

    def load_transactions(self):
        """Read the raw file and describe what is in it."""
        raw_rows = read_csv(self.source_file)

        self.rows = []
        self.exceptions = []
        for line_number, row in enumerate(raw_rows, start=2):  # line 1 is the header
            row["source_line"] = line_number
            self.rows.append(row)

        self.rows_loaded = len(self.rows)
        self.done = {"load": True, "dates": False, "period": False, "amounts": False, "duplicates": False}

        # Count which date formats appear, to show how messy the file is.
        formats_found = {}
        for row in self.rows:
            name = self.date_format_name(row["date"]) or "unreadable"
            formats_found[name] = formats_found.get(name, 0) + 1

        empty_amounts = sum(1 for row in self.rows if not row["amount_czk"].strip())

        return {
            "file": self.source_file.name,
            "rows_loaded": self.rows_loaded,
            "columns": list(raw_rows[0].keys()) if raw_rows else [],
            "date_formats_found": formats_found,
            "rows_with_empty_amount": empty_amounts,
        }

    def date_format_name(self, text):
        """Return the name of the date format of text, or None if unknown."""
        for date_format, name in config.DATE_FORMATS.items():
            try:
                datetime.strptime(text.strip(), date_format)
                return name
            except ValueError:
                continue
        return None

    def standardize_dates(self):
        """Convert every date to YYYY-MM-DD. Unreadable dates become exceptions."""
        self.require("load", "Load the transactions first (load_transactions).")

        converted = 0
        unreadable = []
        kept_rows = []
        for row in self.rows:
            original = row["date"].strip()
            new_date = None
            for date_format in config.DATE_FORMATS:
                try:
                    new_date = datetime.strptime(original, date_format).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

            if new_date is None:
                self.set_aside(row, "unreadable date", f"Date '{original}' matches no known format")
                unreadable.append(row["source_line"])
                continue

            if new_date != original:
                converted += 1
            row["date"] = new_date
            kept_rows.append(row)

        self.rows = kept_rows
        self.done["dates"] = True
        return {
            "dates_converted": converted,
            "dates_already_correct": len(kept_rows) - converted,
            "unreadable_dates_set_aside": unreadable,
        }

    def flag_missing_amounts(self):
        """Set aside rows whose amount is empty or not a number. Never guesses."""
        self.require("load", "Load the transactions first (load_transactions).")

        set_aside = []
        kept_rows = []
        for row in self.rows:
            text = row["amount_czk"].strip()
            if text == "":
                self.set_aside(row, "missing amount", "Amount is empty - not guessed, needs to be checked")
                set_aside.append({"source_line": row["source_line"], "description": row["description"]})
                continue
            try:
                # Decimal instead of float: exact for money, no rounding surprises.
                row["amount_czk"] = str(Decimal(text).quantize(Decimal("0.01")))
            except InvalidOperation:
                self.set_aside(row, "invalid amount", f"Amount '{text}' is not a number")
                set_aside.append({"source_line": row["source_line"], "description": row["description"]})
                continue
            kept_rows.append(row)

        self.rows = kept_rows
        self.done["amounts"] = True
        return {"rows_set_aside": set_aside, "rows_with_valid_amount": len(kept_rows)}

    def set_aside_outside_period(self):
        """Cut-off: set aside every row dated outside the report month."""
        self.require("dates", "Standardize the dates first (standardize_dates).")

        outside = []
        kept_rows = []
        for row in self.rows:
            if not in_report_month(row["date"]):
                self.set_aside(row, "outside the period",
                               f"Dated {row['date']}, outside {config.month_name()} - belongs to another period")
                outside.append({"source_line": row["source_line"], "date": row["date"],
                                "description": row["description"]})
                continue
            kept_rows.append(row)

        self.rows = kept_rows
        self.done["period"] = True
        return {"report_month": config.REPORT_MONTH, "outside_the_period_set_aside": outside,
                "rows_remaining": len(kept_rows)}

    def remove_duplicates(self):
        """Set aside rows that look like a second copy of an earlier row.
        The first occurrence stays in the clean data.

        - PROBABLE duplicate: identical date, description, counterparty and amount.
        - POSSIBLE duplicate: same counterparty and amount within
          config.DUPLICATE_WINDOW_DAYS days, even if worded differently.

        Both can also be real separate charges (e.g. two hotel rooms). They are
        excluded from the totals, but always listed in the report so a person
        can confirm them against the bank statement."""
        # Dates must be in one format first, otherwise "03.09.2026" and
        # "2026-09-03" look different and a duplicate would be missed.
        # The same goes for amounts: "-1840" and "-1840.00" must compare equal.
        self.require("dates", "Standardize the dates first (standardize_dates), "
                              "otherwise duplicates with different date formats are missed.")
        self.require("amounts", "Check the amounts first (flag_missing_amounts), "
                                "so all amounts are written the same way before comparing.")

        first_seen = {}   # the 4 matching fields -> line number of the first occurrence
        duplicates = []
        kept_rows = []
        for row in self.rows:
            key = (row["date"], row["description"].strip(), row["counterparty"].strip(), row["amount_czk"].strip())
            if key in first_seen:
                original_line = first_seen[key]
                self.set_aside(row, "probable duplicate",
                               f"Identical to line {original_line} - confirm against the bank statement")
                duplicates.append({
                    "source_line": row["source_line"],
                    "duplicate_of_line": original_line,
                    "description": row["description"],
                    "amount_czk": row["amount_czk"],
                })
                continue
            first_seen[key] = row["source_line"]
            kept_rows.append(row)

        # Second pass: the same charge with different wording.
        possible = []
        later_copies = set()
        for row, earlier in possible_duplicate_pairs(kept_rows):
            gap = days_between(row["date"], earlier["date"])
            days = "same date" if gap == 0 else f"{gap} day{'s' if gap > 1 else ''} apart"
            self.set_aside(row, "possible duplicate",
                           f"Same counterparty and amount as line {earlier['source_line']} ({days}), "
                           f"different wording - confirm against the bank statement")
            possible.append({"source_line": row["source_line"], "duplicate_of_line": earlier["source_line"],
                             "description": row["description"], "amount_czk": row["amount_czk"]})
            later_copies.add(row["source_line"])
        kept_rows = [row for row in kept_rows if row["source_line"] not in later_copies]

        self.rows = kept_rows
        self.done["duplicates"] = True
        return {"probable_duplicates_set_aside": duplicates, "possible_duplicates_set_aside": possible,
                "rows_remaining": len(kept_rows)}

    def save_cleaned_data(self):
        """Write the clean data and the exceptions list, after checking that
        every loaded row is accounted for."""
        self.require("dates", "Dates are not standardized yet (standardize_dates).")
        self.require("period", "Rows outside the report month are not set aside yet (set_aside_outside_period).")
        self.require("amounts", "Amounts are not checked yet (flag_missing_amounts).")
        self.require("duplicates", "Duplicates are not removed yet (remove_duplicates).")

        # Reconciliation: rows loaded = clean rows + exceptions. If not, stop.
        accounted_for = len(self.rows) + len(self.exceptions)
        if accounted_for != self.rows_loaded:
            raise RuntimeError(f"Reconciliation failed: {self.rows_loaded} rows loaded, "
                               f"but {accounted_for} accounted for")

        # Keep the original file order in both files.
        self.rows.sort(key=lambda row: row["source_line"])
        self.exceptions.sort(key=lambda row: row["source_line"])

        clean_path = self.output_dir / config.CLEAN_FILE_NAME
        exceptions_path = self.output_dir / config.EXCEPTIONS_FILE_NAME
        write_csv(clean_path, self.rows, CLEAN_COLUMNS)
        write_csv(exceptions_path, self.exceptions, EXCEPTION_COLUMNS)

        issues = {}
        for exception in self.exceptions:
            issues[exception["issue"]] = issues.get(exception["issue"], 0) + 1

        return {
            "clean_file": clean_path.name,
            "exceptions_file": exceptions_path.name,
            "rows_loaded": self.rows_loaded,
            "clean_rows": len(self.rows),
            "exceptions": len(self.exceptions),
            "exceptions_by_issue": issues,
            "reconciliation": f"{self.rows_loaded} loaded = {len(self.rows)} clean + "
                              f"{len(self.exceptions)} exceptions - OK",
        }


def make_collector_tools(cleaner):
    """The Collector's tool list: what each tool does and which function runs it.
    None of these tools need inputs from the AI, so the schemas are empty."""
    no_inputs = {"type": "object", "properties": {}}
    return [
        {
            "name": "load_transactions",
            "description": "Read the raw transactions file. Returns the number of rows, "
                           "the date formats found and how many amounts are empty.",
            "input_schema": no_inputs,
            "function": cleaner.load_transactions,
        },
        {
            "name": "standardize_dates",
            "description": "Convert all dates to YYYY-MM-DD. Rows with an unreadable date are "
                           "moved to the exceptions list.",
            "input_schema": no_inputs,
            "function": cleaner.standardize_dates,
        },
        {
            "name": "set_aside_outside_period",
            "description": "Cut-off: move rows dated outside the report month to the exceptions list. "
                           "Needs standardized dates.",
            "input_schema": no_inputs,
            "function": cleaner.set_aside_outside_period,
        },
        {
            "name": "flag_missing_amounts",
            "description": "Move rows with an empty or non-numeric amount to the exceptions list. "
                           "Amounts are never guessed.",
            "input_schema": no_inputs,
            "function": cleaner.flag_missing_amounts,
        },
        {
            "name": "remove_duplicates",
            "description": "Move second copies to the exceptions list, keeping the first occurrence: "
                           "identical rows as probable duplicates, and rows with the same counterparty and "
                           f"amount within {config.DUPLICATE_WINDOW_DAYS} days as possible duplicates. "
                           "Needs standardized dates and checked amounts.",
            "input_schema": no_inputs,
            "function": cleaner.remove_duplicates,
        },
        {
            "name": "save_cleaned_data",
            "description": "Save the clean data and the exceptions list, after checking that every "
                           "loaded row is either clean or an exception. Call this last.",
            "input_schema": no_inputs,
            "function": cleaner.save_cleaned_data,
        },
    ]
