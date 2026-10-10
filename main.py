"""LedgerMind - starts the company.

Stage 3: runs the Bookkeeping department (Collector, then Categorizer) and
prints the exceptions list and the number of transactions per category.
From Stage 5 the Manager will run the departments instead.

Without ANTHROPIC_API_KEY set, the agents run in test mode with a fake model.
"""

import config
from agents import categorizer, collector
from agents.action_log import ActionLog
from agents.models import using_real_model
from tools.csv_helpers import read_csv


def print_exceptions():
    exceptions = read_csv(config.OUTPUT_DIR / config.EXCEPTIONS_FILE_NAME)
    print(f"\nEXCEPTIONS ({len(exceptions)} rows set aside, not in the clean data)")
    print(f"{'Line':>4}  {'Date':<10}  {'Description':<34} {'Amount':>10}  Issue")
    for row in exceptions:
        amount = row["amount_czk"] or "(empty)"
        print(f"{row['source_line']:>4}  {row['date']:<10}  {row['description'][:34]:<34} "
              f"{amount:>10}  {row['issue']}: {row['detail']}")


def print_category_counts():
    rows = read_csv(config.OUTPUT_DIR / config.CATEGORIZED_FILE_NAME)
    print(f"\nTRANSACTIONS PER CATEGORY ({len(rows)} clean transactions)")
    for category in config.CATEGORIES:
        count = sum(1 for row in rows if row["category"] == category)
        print(f"  {category:<10} {count:>3}")

    decided_by_ai = [row for row in rows if row["method"] == "AI"]
    print(f"\nDECIDED BY THE AI ({len(decided_by_ai)} rows)")
    for row in decided_by_ai:
        print(f"  line {row['source_line']}: {row['description']} -> {row['category']} ({row['reason']})")


def main():
    if using_real_model():
        print("Mode: REAL model (ANTHROPIC_API_KEY is set)\n")
    else:
        print("Mode: TEST - fake model, no API calls (ANTHROPIC_API_KEY is not set)\n")

    log = ActionLog()
    collector.create_collector(log).run(collector.TASK)
    categorizer.create_categorizer(log).run(categorizer.TASK)

    print_exceptions()
    print_category_counts()
    print(f"\nFiles in {config.OUTPUT_DIR.name}/: {config.CLEAN_FILE_NAME}, "
          f"{config.EXCEPTIONS_FILE_NAME}, {config.CATEGORIZED_FILE_NAME}")
    print(f"Full log: {log.path}")


if __name__ == "__main__":
    main()
