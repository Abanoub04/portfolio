"""LedgerMind - starts the company.

Stage 1 only sets up the project, so for now this just checks that the
input files are in place. The Manager will be started here in Stage 5.
"""

import config


def main():
    print(f"LedgerMind - report month {config.REPORT_MONTH} ({config.CURRENCY})")
    for path in [config.TRANSACTIONS_FILE, config.BUDGET_FILE]:
        status = "found" if path.exists() else "MISSING"
        print(f"  {path.relative_to(config.PROJECT_ROOT)}: {status}")
    print("The agents are not built yet (coming in Stages 2-5).")


if __name__ == "__main__":
    main()
