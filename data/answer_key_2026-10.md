# Fake data – October 2026 (second test month)

All data is invented. Same fictional company as September (Studio Vltava
s.r.o., Prague design studio, CZK). File: `transactions_2026-10.csv`,
same columns and sign convention (expenses negative, income positive).

47 rows as delivered. Otherwise clean (a few dates in DD.MM.YYYY and
DD/MM/YYYY, no missing amounts, no exact duplicates), with four NEW
problems that September did not have:

| Problem | Line | Row | Correct treatment |
|---|---:|---|---|
| Duplicate with slightly different wording | 6 | "Adobe CC subscription - 3 seats", same date, counterparty and amount as line 5 ("Adobe Creative Cloud (3 seats)") | Probable duplicate of line 5: set aside, confirm against the bank statement |
| Transaction dated in the wrong month | 32 | Office supplies - printer toner, dated 28.09.2026 | Belongs to September: set aside as outside the period, not in October totals |
| Refund (negative expense) | 25 | Refund - Hotel Berlin cancelled night, +3,100 | Travel, reducing Travel spend (a credit, not income) |
| New supplier, no keyword rule | 16 | Taskly team workspace (5 users), Taskly s.r.o. | Software (a team workspace subscription) |

## Answer key (for checking the agents)
Correct treatment: 47 raw rows, 1 probable duplicate and 1 row outside the
period set aside, so **45 rows** in the October data. Category totals with
the refund netted against Travel and Taskly in Software:

| Category | Actual | Budget | vs budget |
|---|---:|---:|---:|
| Salaries | 444 216 | 450 000 | −1 % |
| Rent | 67 500 | 68 000 | −1 % |
| Travel | 3 530 | 15 000 | −76 % |
| Software | 15 610 | 18 000 | −13 % |
| Marketing | 17 400 | 25 000 | −30 % |
| Utilities | 7 870 | 9 000 | −13 % |
| Other | 15 360 | 20 000 | −23 % |
| **Total expenses** | **571 486** | 605 000 | −6 % |
| Sales (income) | 248 500 | – | – |

With these totals no category is more than 20 % over budget. Travel,
Marketing and Other are more than 20 % under budget.
