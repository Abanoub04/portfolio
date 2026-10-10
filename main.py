"""LedgerMind - starts the company.

The owner's request goes to the Manager. The Manager runs Bookkeeping and
Reporting, reviews the report, and either delivers it or escalates.

Without ANTHROPIC_API_KEY set, the agents run in test mode with a fake model.
"""

import config
from agents import manager
from agents.action_log import ActionLog
from agents.models import using_real_model


def show(title, path):
    print("\n" + "=" * 30 + f" {title} " + "=" * 30 + "\n")
    print(path.read_text(encoding="utf-8"))


def main():
    if using_real_model():
        print("Mode: REAL model (ANTHROPIC_API_KEY is set)\n")
    else:
        print("Mode: TEST - fake model, no API calls (ANTHROPIC_API_KEY is not set)\n")

    log = ActionLog()
    the_manager = manager.create_manager(log)
    answer = the_manager.run(manager.TASK)

    out = config.OUTPUT_DIR
    if the_manager.desk.finished == "delivered":
        show("REPORT", out / config.REPORT_FILE_NAME)
    elif the_manager.desk.finished == "escalated":
        show("ESCALATION", out / config.ESCALATION_FILE_NAME)
    show("REVIEW NOTES", out / config.REVIEW_NOTES_FILE_NAME)

    print("=" * 70)
    print(f"Manager: {answer}")
    print(f"Full log: {log.path}")


if __name__ == "__main__":
    main()
