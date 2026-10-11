"""The Manager's checks on the deliverable files.

Each file is opened again and its numbers are read back and compared with
the Analyst's results. Nothing is trusted because "Python wrote it" - a
bug in a generator, or a file edited after it was built, is caught here.

Excel: the formulas have no stored results until Excel opens the file, so
each formula is checked to be exactly the expected formula, and its result
is worked out from the values read back from the same sheet.

Every function returns a list of problems (empty = the file is correct).
"""

import re
from decimal import Decimal, ROUND_HALF_UP

from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from tools.excel_report import (actual_formula, last_transaction_row, percent_formula, sales_formula,
                                 variance_formula)
from tools.writer_tools import numbers_in


def money(text):
    return Decimal(text.replace(",", "").replace("+", ""))


def percent_value(text):
    """'+70.3%' -> Decimal('70.3'); 'n/a' -> None."""
    return None if text == "n/a" else Decimal(text.rstrip("%").replace("+", ""))


def as_decimal(value):
    return Decimal(str(value)) if value is not None else None


def unknown_numbers(text, allowed):
    return sorted({f"{n:,}" for n in numbers_in(text) if n not in allowed})


def word_text(path):
    """All text in a Word file: paragraphs and table cells."""
    document = Document(path)
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        parts += [cell.text for row in table.rows for cell in row.cells]
    return "\n".join(parts)


def slides_text(path):
    """All text on all slides."""
    deck = Presentation(path)
    return "\n".join(shape.text_frame.text for slide in deck.slides for shape in slide.shapes
                     if shape.has_text_frame)


# --- Excel ------------------------------------------------------------------------

def check_excel(path, analysis, categorized, exceptions):
    problems = []
    workbook = load_workbook(path)
    for name in ["Summary", "Transactions", "Exceptions"]:
        if name not in workbook.sheetnames:
            problems.append(f"Excel: sheet '{name}' is missing")
    if problems:
        return problems

    # The Transactions rows as they are in the file: the Summary's SUMIFS
    # formulas are worked out from these.
    transactions = [(values[0], as_decimal(values[4]), values[5])
                    for values in workbook["Transactions"].iter_rows(min_row=2, values_only=True)
                    if values[0] is not None]
    sum_by_category = {}
    for _, amount, category in transactions:
        sum_by_category[category] = sum_by_category.get(category, Decimal(0)) + (amount or 0)
    last_row = last_transaction_row(categorized)

    # Summary: one row per category, then the total row.
    sheet = workbook["Summary"]
    categories = analysis["budget_vs_actual"]["categories"]
    first, last = 2, 1 + len(categories)
    actual_sum = budget_sum = Decimal(0)
    for row, item in enumerate(categories, start=first):
        label = item["category"]
        if sheet.cell(row=row, column=2).value != actual_formula(row, last_row):
            problems.append(f"Excel Summary row {row} ({label}): actual is not the formula "
                            f"{actual_formula(row, last_row)}")
        actual = -sum_by_category.get(label, Decimal(0))       # what the SUMIFS works out to
        budget = as_decimal(sheet.cell(row=row, column=3).value)
        actual_sum += actual
        budget_sum += budget or 0
        problems += check_summary_row(sheet, row, item, label, actual, budget)
    total_row = last + 1
    total = analysis["budget_vs_actual"]["total"]
    expected = {2: f"=SUM(B{first}:B{last})", 3: f"=SUM(C{first}:C{last})"}
    for column, formula in expected.items():
        if sheet.cell(row=total_row, column=column).value != formula:
            problems.append(f"Excel Summary row {total_row}: expected formula {formula}")
    problems += check_summary_row(sheet, total_row, total, "Total expenses", actual_sum, budget_sum)

    # Sales side note: a SUMIFS over the Sales rows.
    sales_formula_found = None
    for row in range(total_row + 1, total_row + 6):
        if sheet.cell(row=row, column=1).value == "Sales income (side note)":
            sales_formula_found = sheet.cell(row=row, column=2).value
    if sales_formula_found != sales_formula(last_row):
        problems.append(f"Excel: sales income is not the formula {sales_formula(last_row)}")
    sales = sum_by_category.get("Sales", Decimal(0))
    if sales != money(analysis["totals"]["sales_income_czk"]):
        problems.append(f"Excel: sales income works out to {sales}, the Analyst says "
                        f"{analysis['totals']['sales_income_czk']}")

    # Transactions: every categorized row, with the same amount and category.
    sheet = workbook["Transactions"]
    found = {}
    for values in sheet.iter_rows(min_row=2, values_only=True):
        if values[0] is not None:
            found[int(values[0])] = (as_decimal(values[4]), values[5])
    expected_rows = {int(r["source_line"]): (Decimal(r["amount_czk"]), r["category"]) for r in categorized}
    if found != expected_rows:
        wrong = sorted(set(found.items()) ^ set(expected_rows.items()))
        problems.append(f"Excel Transactions: {len(found)} rows, {len(expected_rows)} expected; "
                        f"differences on lines {sorted({line for line, _ in wrong})}")

    # Exceptions: every set-aside row.
    sheet = workbook["Exceptions"]
    lines = {int(v[0]) for v in sheet.iter_rows(min_row=2, values_only=True) if isinstance(v[0], int)}
    expected_lines = {int(r["source_line"]) for r in exceptions}
    if lines != expected_lines:
        problems.append(f"Excel Exceptions: lines {sorted(lines)}, expected {sorted(expected_lines)}")
    return problems


def check_summary_row(sheet, row, item, label, actual, budget):
    """One Summary row: label, what the actual works out to, the budget, the two
    variance formulas and what those formulas work out to."""
    problems = []
    where = f"Excel Summary row {row} ({label})"
    if sheet.cell(row=row, column=1).value != label:
        return [f"{where}: label is '{sheet.cell(row=row, column=1).value}'"]
    if actual != money(item["actual_czk"]):
        problems.append(f"{where}: actual works out to {actual}, the Analyst says {item['actual_czk']}")
    if budget != money(item["budget_czk"]):
        problems.append(f"{where}: budget {budget} differs from the Analyst's {item['budget_czk']}")
    if sheet.cell(row=row, column=4).value != variance_formula(row):
        problems.append(f"{where}: variance is not the formula {variance_formula(row)}")
    if sheet.cell(row=row, column=5).value != percent_formula(row):
        problems.append(f"{where}: variance % is not the formula {percent_formula(row)}")
    if actual is not None and budget is not None:
        if actual - budget != money(item["variance_czk"]):
            problems.append(f"{where}: the variance formula gives {actual - budget}, "
                            f"the Analyst says {item['variance_czk']}")
        expected_percent = percent_value(item["variance_percent"])
        if budget != 0:
            percent = ((actual - budget) / budget * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            if percent != expected_percent:
                problems.append(f"{where}: the variance % formula gives {percent}%, "
                                f"the Analyst says {item['variance_percent']}")
    return problems


# --- Word -------------------------------------------------------------------------

def check_word(path, analysis, exceptions, texts, allowed):
    problems = []
    document = Document(path)
    text = "\n".join(p.text for p in document.paragraphs)
    table_text = []
    first_cells = set()
    budget_rows = None
    for table in document.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        table_text += [" ".join(row) for row in rows]
        first_cells |= {row[0] for row in rows[1:]}
        if rows and rows[0] == ["Category", "Actual", "Budget", "Variance", "Variance %"]:
            budget_rows = {row[0].rstrip(" *"): row[1:] for row in rows[1:]}

    # The budget table, cell by cell.
    if budget_rows is None:
        problems.append("Word: the budget vs actual table is missing")
    else:
        expected = analysis["budget_vs_actual"]["categories"] + [analysis["budget_vs_actual"]["total"]]
        for item in expected:
            cells = [item["actual_czk"], item["budget_czk"], item["variance_czk"], item["variance_percent"]]
            if budget_rows.get(item["category"]) != cells:
                problems.append(f"Word budget table, {item['category']}: shows {budget_rows.get(item['category'])}, "
                                f"the Analyst says {cells}")

    # Every number in the document comes from the Analyst.
    unknown = unknown_numbers(text + "\n" + "\n".join(table_text), allowed)
    if unknown:
        problems.append(f"Word: numbers not in the Analyst's results: {unknown}")

    # Same content as the report: the Writer's reviewed text is all there.
    for name, part in texts.items():
        if part and part not in text:
            problems.append(f"Word: the {name.replace('_', ' ')} is missing or different")

    # Every set-aside row is listed.
    missing = sorted(int(r["source_line"]) for r in exceptions if r["source_line"] not in first_cells)
    if missing:
        problems.append(f"Word: set-aside rows missing from the exceptions tables: lines {missing}")
    return problems


# --- PowerPoint ---------------------------------------------------------------------

def check_slides(path, analysis, allowed, max_slides=5):
    problems = []
    deck = Presentation(path)
    if len(deck.slides) > max_slides:
        problems.append(f"PowerPoint: {len(deck.slides)} slides, at most {max_slides} allowed")

    # The charts: every category exactly once, with the Analyst's actual and budget.
    plotted = {}
    texts = []
    for slide in deck.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
            if getattr(shape, "has_chart", False) and shape.has_chart:
                plot = shape.chart.plots[0]
                series = {s.name: list(s.values) for s in plot.series}
                for index, category in enumerate(plot.categories):
                    if category in plotted:
                        problems.append(f"PowerPoint: {category} is plotted twice")
                    plotted[category] = (as_decimal(series["Actual"][index]), as_decimal(series["Budget"][index]))
    expected = {item["category"]: (money(item["actual_czk"]), money(item["budget_czk"]))
                for item in analysis["budget_vs_actual"]["categories"]}
    if plotted != expected:
        wrong = sorted(set(plotted) ^ set(expected) | {c for c in expected if plotted.get(c) != expected[c]})
        problems.append(f"PowerPoint chart: actual/budget differ from the Analyst's results for {wrong}")

    # Headline numbers on the first slide.
    total = analysis["budget_vs_actual"]["total"]
    headline = " ".join(shape.text_frame.text for shape in deck.slides[0].shapes if shape.has_text_frame)
    direction = f"{total['variance_percent'].lstrip('+-')} {total['variance_direction']}"
    for label, value in [("total expenses", total["actual_czk"]), ("budget", total["budget_czk"]),
                         ("variance", total["variance_czk"].lstrip("+-")), ("variance %", direction),
                         ("sales income", analysis["totals"]["sales_income_czk"])]:
        if not re.search(r"(?<![\d,.])" + re.escape(value) + r"(?![\d,])", headline):
            problems.append(f"PowerPoint headline: {label} {value} is missing")

    unknown = unknown_numbers("\n".join(texts), allowed)
    if unknown:
        problems.append(f"PowerPoint: numbers not in the Analyst's results: {unknown}")
    return problems
