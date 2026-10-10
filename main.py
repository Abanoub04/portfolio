"""LedgerMind - starts the company.

Stage 4: runs the Bookkeeping department (Collector, Categorizer) and then
the Reporting department (Analyst, Writer), and prints the finished report.
From Stage 5 the Manager will run the departments instead.

Without ANTHROPIC_API_KEY set, the agents run in test mode with a fake model.
"""

import config
from agents import analyst, categorizer, collector, writer
from agents.action_log import ActionLog
from agents.models import using_real_model


def main():
    if using_real_model():
        print("Mode: REAL model (ANTHROPIC_API_KEY is set)\n")
    else:
        print("Mode: TEST - fake model, no API calls (ANTHROPIC_API_KEY is not set)\n")

    log = ActionLog()

    # Bookkeeping department
    collector.create_collector(log).run(collector.TASK)
    categorizer.create_categorizer(log).run(categorizer.TASK)

    # Reporting department
    analyst.create_analyst(log).run(analyst.TASK)
    writer.create_writer(log).run(writer.TASK)

    report_path = config.OUTPUT_DIR / config.REPORT_FILE_NAME
    print("\n" + "=" * 80 + "\n")
    print(report_path.read_text(encoding="utf-8"))
    print("=" * 80)
    print(f"Report: {report_path}")
    print(f"Full log: {log.path}")


if __name__ == "__main__":
    main()
