"""The PowerPoint deliverable: report_YYYY-MM.pptx, a 4-slide management deck.

Every slide has an action title that states its message, e.g.
"October 5.5% under budget; three categories may have missing costs".
The titles are written by Python from the Analyst's results, with fixed
rules - so every number in them comes from the Analyst.

  1. Headline numbers and the to-do count
  2. Budget vs actual - two bar charts: the large categories (Salaries,
     Rent) dwarf the rest, so they get their own scale
  3. Unusual items
  4. Actions before closing the month
"""

from decimal import Decimal

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Inches, Pt

NAVY = RGBColor(0x1D, 0x33, 0x52)
GREY = RGBColor(0x4A, 0x4A, 0x4A)
LIGHT = RGBColor(0xE8, 0xED, 0xF3)
ACTUAL_COLOR = RGBColor(0x2A, 0x78, 0xD6)   # categorical slot 1 (blue)
BUDGET_COLOR = RGBColor(0xEB, 0x68, 0x34)   # categorical slot 2 (orange) - validated pair
FONT = "Calibri"

# Categories with a budget at least this large go into the "large categories" chart.
LARGE_BUDGET = Decimal(50000)
# A large category within this many percent of budget counts as "close to budget".
CLOSE_TO_BUDGET_PERCENT = Decimal(5)

NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


# --- small helpers ------------------------------------------------------------------

def money(text):
    return Decimal(text.replace(",", "").replace("+", ""))


def unsigned(text):
    """'-33,514' -> '33,514'; '+70.3%' -> '70.3%' (only removes the sign)."""
    return text.lstrip("+-")


def count_words(number, singular, plural):
    word = NUMBER_WORDS[number] if number < len(NUMBER_WORDS) else str(number)
    return f"{word} {singular if number == 1 else plural}"


def join(names):
    """['A'] -> 'A'; ['A', 'B'] -> 'A and B'; ['A', 'B', 'C'] -> 'A, B and C'."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def lines_label(items):
    numbers = [str(x["source_line"]) for x in items]
    return ("line " if len(numbers) == 1 else "lines ") + ", ".join(numbers)


def short_month(analysis):
    from datetime import datetime
    return datetime.strptime(analysis["report_month"], "%Y-%m").strftime("%B")


# --- action titles (one message per slide) --------------------------------------

def headline_title(analysis):
    total = analysis["budget_vs_actual"]["total"]
    unusual = analysis["unusual_items"]
    over = [x["category"] for x in unusual["categories_over_budget"]]
    under = [x["category"] for x in unusual["categories_under_budget"]]
    if total["variance_direction"] == "on budget":
        title = f"{short_month(analysis)} on budget"
    else:
        title = f"{short_month(analysis)} {unsigned(total['variance_percent'])} {total['variance_direction']}"
    parts = []
    if over:
        parts.append(f"{join(over)} overspent")
    if len(under) == 1:
        parts.append(f"{under[0]} may have missing costs")
    elif under:
        parts.append(f"{count_words(len(under), 'category', 'categories')} may have missing costs")
    return title + ("; " + ", ".join(parts) if parts else "")


def chart_title(analysis):
    rows = analysis["budget_vs_actual"]["categories"]
    large = [r for r in rows if money(r["budget_czk"]) >= LARGE_BUDGET]
    biggest = max(rows, key=lambda r: abs(money(r["variance_czk"])))
    close = [r for r in large if r["variance_percent"] != "n/a"
             and abs(Decimal(unsigned(r["variance_percent"]).rstrip("%"))) <= CLOSE_TO_BUDGET_PERCENT]
    lead = f"{join([r['category'] for r in close])} close to budget; " if close and len(close) == len(large) else ""
    return f"{lead}biggest variance: {biggest['category']}, {biggest['variance_phrase']}"


def unusual_title(analysis):
    unusual = analysis["unusual_items"]
    threshold = unusual["over_budget_threshold"]
    over = [x["category"] for x in unusual["categories_over_budget"]]
    under = [x["category"] for x in unusual["categories_under_budget"]]
    if over and under:
        return f"Overspend in {join(over)}; {join(under)} more than {threshold} under budget"
    if over:
        return f"Overspend in {join(over)}: more than {threshold} over budget"
    if under:
        return f"{join(under)} more than {threshold} under budget – check for missing or late costs"
    return f"No category is more than {threshold} away from budget"


# --- drawing ----------------------------------------------------------------------

def text_box(slide, left, top, width, height, paragraphs, size=20, color=None, space_after=10):
    """paragraphs: list of strings or (text, bold) tuples, one per line."""
    frame = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height)).text_frame
    frame.word_wrap = True
    for index, item in enumerate(paragraphs):
        text, bold = item if isinstance(item, tuple) else (item, False)
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        run = paragraph.add_run()
        # A non-breaking space keeps "CZK" on the same line as its amount.
        run.text = text.replace("CZK ", "CZK\u00a0")
        run.font.size, run.font.bold, run.font.name = Pt(size), bold, FONT
        run.font.color.rgb = color or NAVY
        paragraph.space_after = Pt(space_after)
    return frame


def title(slide, text):
    text_box(slide, 0.5, 0.3, 12.3, 1.3, [(text, True)], size=28)


def bullets(slide, top, height, lines, size=20):
    text_box(slide, 0.6, top, 12.1, height, ["• " + line for line in lines], size=size)


def kpi(slide, left, label, value, note=""):
    box = slide.shapes.add_shape(1, Inches(left), Inches(1.75), Inches(2.95), Inches(2.0))  # rectangle
    box.fill.solid()
    box.fill.fore_color.rgb = LIGHT
    box.line.fill.background()
    box.shadow.inherit = False
    text_box(slide, left + 0.15, 1.85, 2.7, 0.5, [label], size=16, color=GREY)
    text_box(slide, left + 0.15, 2.35, 2.7, 0.8, [(value, True)], size=32)
    if note:
        text_box(slide, left + 0.15, 3.1, 2.7, 0.5, [note], size=15, color=GREY)


def bar_chart(slide, left, width, heading, rows):
    text_box(slide, left, 1.55, width, 0.5, [(heading, True)], size=18)
    data = CategoryChartData(number_format='#,##0')
    data.categories = [row["category"] for row in rows]
    data.add_series("Actual", [float(money(row["actual_czk"])) for row in rows])
    data.add_series("Budget", [float(money(row["budget_czk"])) for row in rows])
    shape = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(left), Inches(2.05),
                                   Inches(width), Inches(5.2), data)
    chart = shape.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(14)
    for series, color in zip(chart.series, [ACTUAL_COLOR, BUDGET_COLOR]):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color
    plot = chart.plots[0]
    plot.gap_width = 50
    plot.overlap = -10
    plot.has_data_labels = True
    plot.data_labels.number_format = '#,##0'
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.font.size = Pt(12)
    plot.data_labels.font.color.rgb = GREY
    chart.category_axis.tick_labels.font.size = Pt(14)
    chart.category_axis.reverse_order = True            # first category at the top
    value_axis = chart.value_axis
    value_axis.tick_labels.font.size = Pt(11)
    value_axis.tick_labels.number_format = '#,##0'
    value_axis.tick_labels.number_format_is_linked = False
    value_axis.has_major_gridlines = True
    value_axis.major_gridlines.format.line.color.rgb = LIGHT
    return chart


# --- slides -----------------------------------------------------------------------

def build_presentation(analysis, texts, path, month_label):
    deck = Presentation()
    deck.slide_width, deck.slide_height = Inches(13.333), Inches(7.5)   # 16:9
    blank = deck.slide_layouts[6]

    headline_slide(deck.slides.add_slide(blank), analysis)
    chart_slide(deck.slides.add_slide(blank), analysis)
    unusual_slide(deck.slides.add_slide(blank), analysis, texts)
    closing_slide(deck.slides.add_slide(blank), analysis)
    deck.save(path)


def headline_slide(slide, analysis):
    total = analysis["budget_vs_actual"]["total"]
    totals = analysis["totals"]
    title(slide, headline_title(analysis))
    kpi(slide, 0.5, "Total expenses (CZK)", total["actual_czk"])
    kpi(slide, 3.6, "Budget (CZK)", total["budget_czk"])
    kpi(slide, 6.7, "Variance (CZK)", unsigned(total["variance_czk"]),
        f"{unsigned(total['variance_percent'])} {total['variance_direction']}")
    kpi(slide, 9.8, "Sales income (CZK)", totals["sales_income_czk"], "side note")

    # The category detail is on slide 3; here only the to-do line.
    excluded, to_review = closing_actions(analysis)
    panel(slide, 0.5, 4.25, 12.25, 1.45, "Before closing",
          [f"{count_words(len(excluded) + len(to_review), 'action', 'actions').capitalize()} "
           f"to clear – see the last slide"], size=24, bullet=False)


def chart_slide(slide, analysis):
    rows = analysis["budget_vs_actual"]["categories"]
    large = [row for row in rows if money(row["budget_czk"]) >= LARGE_BUDGET]
    small = [row for row in rows if money(row["budget_czk"]) < LARGE_BUDGET]
    title(slide, chart_title(analysis))
    if large:
        bar_chart(slide, 0.5, 4.6, "Large categories", large)
    if small:
        bar_chart(slide, 5.3 if large else 0.5, 7.5 if large else 12.3, "Other categories", small)


def unusual_slide(slide, analysis, texts):
    unusual = analysis["unusual_items"]
    refunds = analysis["totals"].get("refunds", {})
    lines = [f"{x['category']}: actual {x['actual_czk']} vs budget {x['budget_czk']}, {x['variance_phrase']}"
             + refund_note(refunds.get(x["category"]), "over")
             for x in unusual["categories_over_budget"]]
    lines += [f"{x['category']}: actual {x['actual_czk']} vs budget {x['budget_czk']}, {x['variance_phrase']}"
              + refund_note(refunds.get(x["category"]), "under")
              for x in unusual["categories_under_budget"]]
    flagged = {x["category"] for x in unusual["categories_over_budget"] + unusual["categories_under_budget"]}
    lines += [f"{category}: actual reduced by a refund of CZK {refund['total_czk']} ({refund_lines(refund)})"
              for category, refund in refunds.items() if category not in flagged]
    if unusual["large_transactions"]:
        lines += [f"Line {x['source_line']}: {x['description']} ({x['category']}) – {x['amount_czk']}"
                  for x in unusual["large_transactions"]]
    else:
        lines.append(f"No single expense above {unusual['large_transaction_threshold_czk']} outside "
                     f"{' and '.join(unusual['large_transactions_excluding'])}")
    title(slide, unusual_title(analysis))
    bullets(slide, 1.65, 3.3, lines, size=22)
    # The Writer's explanation of what drove the overspend - only when there is
    # an overspend to explain, so the slide never repeats the bullets.
    comment = texts.get("unusual_items_comment", "")
    under = [x["category"] for x in unusual["categories_under_budget"]]
    if comment and unusual["categories_over_budget"]:
        panel(slide, 0.5, 4.95, 12.3, 2.25, "What drove the overspend", [comment], size=18, bullet=False)
    elif under:
        panel(slide, 0.5, 4.95, 12.3, 2.0, "What to check", [
            f"Spending far below budget is not automatically a saving. For {join(under)}, ask whether "
            f"supplier invoices are still to come or were booked late, and accrue them before closing "
            f"the month."], size=20, bullet=False)


def refund_lines(refund):
    return ("line " if len(refund["lines"]) == 1 else "lines ") + ", ".join(str(n) for n in refund["lines"])


def refund_note(refund, direction):
    """A refund lowers the category's actual: it widens an under-budget gap
    and hides part of an overspend. Both are worth saying."""
    if not refund:
        return ""
    if direction == "under":
        return f"; CZK {refund['total_czk']} of the gap is a refund ({refund_lines(refund)})"
    return f"; after a refund of CZK {refund['total_czk']} ({refund_lines(refund)})"


def closing_actions(analysis):
    """(excluded, to_review): actions for rows kept out of the totals, and for
    rows included in the totals that a person must check."""
    exceptions = analysis["exceptions"]
    excluded = []
    if exceptions["probable_duplicates_count"]:
        excluded.append(f"Confirm {count_words(exceptions['probable_duplicates_count'], 'probable duplicate', 'probable duplicates')} "
                        f"against the bank statement ({lines_label(exceptions['probable_duplicates'])}; "
                        f"CZK {exceptions['probable_duplicates_total_czk']})")
    if exceptions["possible_duplicates_count"]:
        excluded.append(f"Confirm {count_words(exceptions['possible_duplicates_count'], 'possible duplicate', 'possible duplicates')} "
                        f"against the bank statement ({lines_label(exceptions['possible_duplicates'])}; "
                        f"CZK {exceptions['possible_duplicates_total_czk']})")
    if exceptions["outside_the_period_count"]:
        excluded.append(f"Book {count_words(exceptions['outside_the_period_count'], 'row', 'rows')} from another "
                        f"period in its own month ({lines_label(exceptions['outside_the_period'])})")
    if exceptions["missing_amounts_count"]:
        excluded.append(f"Obtain {count_words(exceptions['missing_amounts_count'], 'missing amount', 'missing amounts')} "
                        f"({lines_label(exceptions['missing_amounts'])}); until then their categories are understated")
    to_review = [f"Line {item['source_line']}: {item['description']} – {item['category']}, {item['amount_czk']}"
                 for item in exceptions["needs_review"]]
    return excluded, to_review


def estimated_height(lines, width, size, spacing=0.25):
    """Rough height in inches of wrapped text: characters per line from the
    box width and font size."""
    characters_per_line = max(10, int(width * 72 / (size * 0.5)))
    rows = sum(-(-len(line) // characters_per_line) for line in lines)
    return rows * size * 1.25 / 72 + len(lines) * spacing


def panel(slide, left, top, width, height, heading, lines, size=20, bullet=True):
    box = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))  # rectangle
    box.fill.solid()
    box.fill.fore_color.rgb = LIGHT
    box.line.fill.background()
    box.shadow.inherit = False
    text_box(slide, left + 0.2, top + 0.15, width - 0.4, 0.5, [(heading, True)], size=size)
    text_box(slide, left + 0.2, top + 0.75, width - 0.4, height - 0.9,
             [("• " if bullet else "") + line for line in lines], size=size - 2, space_after=12)


def closing_slide(slide, analysis):
    excluded, to_review = closing_actions(analysis)
    count = len(excluded) + len(to_review)
    month = short_month(analysis)
    if not count:
        title(slide, f"Nothing to clear before closing {month}")
        return
    title(slide, f"{count_words(count, 'action', 'actions').capitalize()} before closing {month}")
    groups = [(heading, lines) for heading, lines in
              [("Excluded from the totals – confirm", excluded), ("Included in the totals – review", to_review)]
              if lines]
    width = 12.3 if len(groups) == 1 else 6.0
    size = 26
    # Both panels as tall as the longer list needs (so they line up), right
    # under the title.
    height = min(5.6, 1.2 + max(estimated_height(["• " + line for line in lines], width - 0.4, size - 2)
                                for _, lines in groups))
    top = 1.6
    for index, (heading, lines) in enumerate(groups):
        panel(slide, 0.5 + index * 6.3, top, width, height, heading, lines, size=size)
