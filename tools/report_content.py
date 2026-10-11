"""The monthly report as a list of content blocks, built from the Analyst's
results and the Writer's three text parts.

The same blocks are rendered as Markdown (the draft the Manager reviews) and
as a Word document, so both always have the same content. Every number in a
block comes straight from the analysis - nothing is calculated here.

Block types:
    {"type": "heading", "level": 1, "text": "..."}
    {"type": "paragraph", "runs": [("text", bold), ...]}
    {"type": "bullets", "items": [[("text", bold), ...], ...]}
    {"type": "table", "headers": [...], "rows": [[...], ...],
     "align": ["left" | "right", ...], "bold_last_row": bool}
"""

from datetime import datetime


def month_name(analysis):
    return datetime.strptime(analysis["report_month"], "%Y-%m").strftime("%B %Y")


def heading(level, text):
    return {"type": "heading", "level": level, "text": text}


def paragraph(*runs):
    """paragraph("plain") or paragraph(("bold part", True), (" rest", False))."""
    return {"type": "paragraph", "runs": [run if isinstance(run, tuple) else (run, False) for run in runs]}


def bullets(items):
    return {"type": "bullets", "items": items}


def table(headers, rows, align=None, bold_last_row=False):
    """A table, or the paragraph "None." when there are no rows."""
    if not rows:
        return [paragraph("None.")]
    return [{"type": "table", "headers": headers, "rows": [[str(cell) for cell in row] for row in rows],
             "align": align or ["left"] * len(headers), "bold_last_row": bold_last_row}]


def build_content(analysis, texts):
    """All blocks of the report. texts: summary, unusual_items_comment, exceptions_comment."""
    blocks = [
        heading(1, f"Monthly expense report – {month_name(analysis)}"),
        paragraph(f"All amounts in {analysis['currency']}. Prepared by LedgerMind."),
        heading(2, "Summary"),
        paragraph(texts["summary"].strip()),
    ]
    blocks += budget_section(analysis)
    blocks += unusual_section(analysis, texts["unusual_items_comment"].strip())
    blocks += exceptions_section(analysis, texts.get("exceptions_comment", "").strip())
    return blocks


def budget_section(analysis):
    budget = analysis["budget_vs_actual"]
    totals = analysis["totals"]
    understated = analysis["exceptions"]["understated_categories"]
    rows = []
    for row in budget["categories"]:
        # A * marks categories whose actual is understated (amounts still missing).
        name = row["category"] + (" *" if row["category"] in understated else "")
        rows.append([name, row["actual_czk"], row["budget_czk"], row["variance_czk"], row["variance_percent"]])
    total = budget["total"]
    rows.append([total["category"], total["actual_czk"], total["budget_czk"],
                 total["variance_czk"], total["variance_percent"]])

    blocks = [heading(2, "Budget vs actual")]
    blocks += table(["Category", "Actual", "Budget", "Variance", "Variance %"], rows,
                    align=["left", "right", "right", "right", "right"], bold_last_row=True)
    if understated:
        parts = [f"{category} (line {', '.join(str(n) for n in found)})" for category, found in understated.items()]
        blocks.append(paragraph(f"* Actual understated – amount still missing for: {'; '.join(parts)}. "
                                f"See Exceptions."))
    blocks.append(paragraph(f"{budget['note']}."))
    blocks.append(paragraph(f"Side note: sales income for the month was {totals['sales_income_czk']} "
                            f"({totals['sales_transactions']} transactions)."))
    return blocks


def unusual_section(analysis, comment):
    unusual = analysis["unusual_items"]
    threshold = unusual["over_budget_threshold"]
    blocks = [heading(2, "Unusual items")]

    blocks.append(paragraph((f"Categories more than {threshold} over budget", True)))
    items = []
    for item in unusual["categories_over_budget"]:
        largest = ", ".join(f"{x['description']} {x['amount_czk']}" for x in item.get("largest_items", []))
        items.append([(item["category"], True),
                      (f": actual {item['actual_czk']} vs budget {item['budget_czk']} "
                       f"({item['variance_czk']}, {item['variance_percent']}). Largest items: {largest}.", False)])
    blocks.append(bullets(items or [[("None.", False)]]))

    blocks.append(paragraph((f"Categories more than {threshold} under budget", True)))
    items = []
    for item in unusual["categories_under_budget"]:
        items.append([(item["category"], True),
                      (f": actual {item['actual_czk']} vs budget {item['budget_czk']} "
                       f"({item['variance_czk']}, {item['variance_percent']}). Note: {item['note']}.", False)])
    blocks.append(bullets(items or [[("None.", False)]]))

    excluded = " and ".join(unusual["large_transactions_excluding"])
    blocks.append(paragraph((f"Single expenses above {unusual['large_transaction_threshold_czk']} "
                             f"(excluding {excluded})", True)))
    items = [[(f"Line {x['source_line']}, {x['date']}: {x['description']} ({x['category']}) – {x['amount_czk']}",
               False)] for x in unusual["large_transactions"]]
    blocks.append(bullets(items or [[("None.", False)]]))

    if comment:
        blocks.append(paragraph(comment))
    return blocks


def exceptions_section(analysis, comment):
    exceptions = analysis["exceptions"]
    blocks = [heading(2, "Exceptions")]
    amount_table = ["Line", "Date", "Description", "Amount", "Note"]

    blocks.append(paragraph(
        ("Probable duplicates – confirm against the bank statement", True),
        f" ({exceptions['probable_duplicates_count']}, total {exceptions['probable_duplicates_total_czk']}) – "
        f"identical to an earlier row, so excluded from all totals above; if a row turns out "
        f"to be a real separate charge, its amount must be added back"))
    blocks += table(amount_table, [[x["source_line"], x["date"], x["description"], x["amount_czk"], x["detail"]]
                                   for x in exceptions["probable_duplicates"]])

    blocks.append(paragraph(
        ("Possible duplicates – confirm against the bank statement", True),
        f" ({exceptions['possible_duplicates_count']}, total {exceptions['possible_duplicates_total_czk']}) – "
        f"same counterparty and amount as an earlier row within {exceptions['duplicate_window_days']} days, "
        f"but worded differently; excluded from all totals above until confirmed"))
    blocks += table(amount_table, [[x["source_line"], x["date"], x["description"], x["amount_czk"], x["detail"]]
                                   for x in exceptions["possible_duplicates"]])

    blocks.append(paragraph(
        ("Outside the period", True),
        f" ({exceptions['outside_the_period_count']}) – dated outside {month_name(analysis)}, so not included "
        f"in this month's totals; book them in their own month"))
    blocks += table(amount_table, [[x["source_line"], x["date"], x["description"], x["amount_czk"], x["detail"]]
                                   for x in exceptions["outside_the_period"]])

    blocks.append(paragraph(
        ("Missing amounts to follow up", True),
        f" ({exceptions['missing_amounts_count']}) – not included in the totals until the amount is known, "
        f"so the actual of the likely category is understated"))
    blocks += table(["Line", "Date", "Description", "Counterparty", "Likely category"],
                    [[x["source_line"], x["date"], x["description"], x["counterparty"], x["likely_category"]]
                     for x in exceptions["missing_amounts"]])

    blocks.append(paragraph(
        ("Items needing review", True),
        f" ({exceptions['needs_review_count']}) – included in the totals, category to be confirmed "
        f"(a refund reduces its category)"))
    blocks += table(["Line", "Date", "Description", "Category", "Amount", "To check"],
                    [[x["source_line"], x["date"], x["description"], x["category"], x["amount_czk"],
                      x["review_reason"]] for x in exceptions["needs_review"]])

    if exceptions["other_issues"]:
        blocks.append(paragraph((f"Other data issues ({len(exceptions['other_issues'])})", True)))
        blocks += table(["Line", "Issue", "Detail"],
                        [[x["source_line"], x["issue"], x["detail"]] for x in exceptions["other_issues"]])

    if comment:
        blocks.append(paragraph(comment))
    return blocks


# --- Markdown -------------------------------------------------------------------

def markdown_runs(runs):
    text = "".join(f"**{t}**" if bold else t for t, bold in runs)
    # A plain line starting with "*" would turn into a list item in Markdown.
    if runs and not runs[0][1] and text.startswith("*"):
        text = "\\" + text
    return text


def render_markdown(blocks):
    lines = []
    for block in blocks:
        if block["type"] == "heading":
            lines.append("#" * block["level"] + " " + block["text"])
        elif block["type"] == "paragraph":
            lines.append(markdown_runs(block["runs"]))
        elif block["type"] == "bullets":
            lines += ["- " + markdown_runs(item) for item in block["items"]]
        elif block["type"] == "table":
            lines.append("| " + " | ".join(block["headers"]) + " |")
            lines.append("|" + "".join("---:|" if a == "right" else "---|" for a in block["align"]))
            for index, row in enumerate(block["rows"]):
                last = index == len(block["rows"]) - 1
                cells = [f"**{cell}**" if (last and block["bold_last_row"]) else cell for cell in row]
                lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
