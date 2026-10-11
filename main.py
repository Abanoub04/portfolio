"""LedgerMind - starts the company.

The owner's request goes to the Manager. The Manager runs Bookkeeping and
Reporting, reviews the report, and either delivers it or escalates.
Afterwards a run check reports HARD checks (must always pass) and SOFT
differences from the answer key (the AI's judgement calls).

Without ANTHROPIC_API_KEY set (in the environment or in .env), the agents
run in test mode with a fake model and nothing is sent to the API.

Options:
    python main.py                   September 2026, real model if a key is set
    python main.py --month 2026-10   another month (data/transactions_2026-10.csv)
    python main.py --test            force test mode, even if a key is set
"""

import argparse
import sys

import config
from agents import manager
from agents.action_log import ActionLog
from agents.base_agent import AgentError
from agents import models
from agents.models import placeholder_key_set, using_real_model
from tools.run_checks import RunCheck, format_run_check


def show(title, path):
    if not path.exists():
        return
    print("\n" + "=" * 30 + f" {title} " + "=" * 30 + "\n")
    print(path.read_text(encoding="utf-8"))


def explain_api_error(error):
    """A plain-English message for the most common API problems."""
    import anthropic
    if isinstance(error, anthropic.AuthenticationError):
        return "The API key was rejected. Check ANTHROPIC_API_KEY in your .env file."
    if isinstance(error, anthropic.PermissionDeniedError):
        return "The API key has no access to this model. Check your account or change MODEL in config.py."
    if isinstance(error, anthropic.NotFoundError):
        return f"Model '{config.MODEL}' was not found. Check MODEL in config.py."
    if isinstance(error, anthropic.RateLimitError):
        return "Rate limit or credit limit reached. Wait a minute, or check your credit balance."
    if isinstance(error, anthropic.APIConnectionError):
        return "Could not reach the API. Check your internet connection."
    if isinstance(error, anthropic.APIStatusError):
        return f"The API returned an error ({error.status_code}): {error.message}"
    return None


def parse_arguments():
    parser = argparse.ArgumentParser(description="Run LedgerMind for one month.")
    parser.add_argument("--month", default=config.DEFAULT_MONTH,
                        help=f"month to report on, YYYY-MM (default {config.DEFAULT_MONTH})")
    parser.add_argument("--test", action="store_true",
                        help="force test mode (fake model, no API calls) even if a key is set")
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    config.set_month(arguments.month)
    if not config.TRANSACTIONS_FILE.exists():
        print(f"No transactions file for {arguments.month}: {config.TRANSACTIONS_FILE} not found.")
        return 2
    if arguments.test:
        models.force_test_mode()

    if placeholder_key_set():
        print("Your .env still contains the placeholder 'your-key-here'. Put your real key in .env,\n"
              "or remove the line to run in test mode.")
        return 2

    if using_real_model():
        print(f"Mode: REAL model {config.MODEL} (ANTHROPIC_API_KEY is set) - this run uses API credit")
    elif arguments.test:
        print("Mode: TEST - fake model, no API calls (forced with --test)")
    else:
        print("Mode: TEST - fake model, no API calls (ANTHROPIC_API_KEY is not set)")
    print(f"Month: {config.month_name()} ({config.TRANSACTIONS_FILE.name})\n")

    log = ActionLog()
    the_manager = manager.create_manager(log)
    try:
        answer = the_manager.run(manager.task())
    except AgentError as error:
        # e.g. the safety brake (too many steps) or a refused/cut-off answer
        print(f"\nThe run stopped: {error}\nFull log: {log.path}")
        return 1
    except Exception as error:
        message = explain_api_error(error) if using_real_model() else None
        if message is None:
            raise
        print(f"\nThe run stopped: {message}\nFull log: {log.path}")
        return 1

    out = config.OUTPUT_DIR
    if the_manager.desk.finished == "delivered":
        show("REPORT", out / config.REPORT_FILE_NAME)
    elif the_manager.desk.finished == "escalated":
        show("ESCALATION", out / config.ESCALATION_FILE_NAME)
    show("REVIEW NOTES", out / config.REVIEW_NOTES_FILE_NAME)

    check = RunCheck(outcome=the_manager.desk.finished, writer_runs=the_manager.desk.writer_runs).run()
    check_text = format_run_check(check)
    (out / config.RUN_CHECK_FILE_NAME).write_text(check_text, encoding="utf-8")
    show("RUN CHECK", out / config.RUN_CHECK_FILE_NAME)

    print("=" * 70)
    print(f"Manager: {answer}")
    print(f"Files in {out.name}/, full log: {log.path}")
    if not check["hard_passed"]:
        print("A HARD check failed. This is not an AI judgement call: the code got something wrong or does\n"
              "not handle something in this data yet. See the run check above.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
