# Fake data – September 2026

All data is invented. The company is a fictional Prague design studio
("Studio Vltava s.r.o."), 6 employees, amounts in CZK.

## transactions.csv
Columns: `date, description, counterparty, amount_czk`
Sign convention: **expenses are negative, income (Sales) is positive.**

61 rows as delivered, with this planted mess:

| Problem | Rows |
|---|---|
| Mixed date formats | `2026-09-03` (ISO), `03.09.2026` (Czech), `02/09/2026` (DD/MM/YYYY – never US order) |
| Exact duplicate | Office supplies 05.09 (−1 840) |
| Same transaction exported twice in different date formats | Hotel Brno (−3 400), Google Ads (−12 000), Hotel Berlin (−9 200) |
| Missing amount | Figma Professional, Courier – documents to client, Taxi Berlin airport |
| Unclear category on purpose | Card payment ALBERT, Card payment ALZA.CZ, Transfer – P. Kratochvíl |

## budget.csv
Monthly expense budget per category (positive numbers, CZK). No budget for Sales.

## Answer key (for checking the agents later)
After removing the 4 duplicates: **57 rows**, of which 3 have no amount.
Totals of the 54 rows with an amount, using the obvious category for each row
(the three unclear items counted as Other):

| Category | Actual | Budget | vs budget |
|---|---:|---:|---:|
| Salaries | 444 216 | 450 000 | −1 % |
| Rent | 67 500 | 68 000 | −1 % |
| Marketing | 42 000 | 25 000 | **+68 %** |
| Travel | 25 546 | 15 000 | **+70 %** |
| Other | 23 132 | 20 000 | +16 % (below the 20 % flag) |
| Software | 12 630 | 18 000 | −30 % |
| Utilities | 7 870 | 9 000 | −13 % |
| **Total expenses** | **622 894** | 605 000 | +3 % |
| Sales (income) | 371 000 | – | – |
