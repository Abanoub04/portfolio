"""LedgerMind - starts the company.

Stage 2: the agents are not built yet, so this runs one demo agent to show
the agent engine and the action log working. The Manager takes over here
in Stage 5.

Without ANTHROPIC_API_KEY set, the demo runs in test mode with a fake model.
"""

from agents.action_log import ActionLog
from agents.base_agent import Agent
from agents.models import using_real_model
from tools.demo_tools import COUNT_ROWS_TOOL

DEMO_INSTRUCTIONS = (
    "You are a demo agent at LedgerMind, a small accounting firm. "
    "Use your tools to answer; never guess numbers. Answer in one sentence."
)

DEMO_TASK = "How many rows do transactions.csv and budget.csv each have?"

# What the agent does in test mode, step by step.
# The fake model also tries one file that doesn't exist, to show how
# a tool error is logged and handed back instead of crashing the run.
DEMO_FAKE_SCRIPT = [
    {"tool": "count_rows", "input": {"file_name": "transactions.csv"}},
    {"tool": "count_rows", "input": {"file_name": "budgett.csv"}},
    {"tool": "count_rows", "input": {"file_name": "budget.csv"}},
    {"text": "(test mode) Done - the row counts are in the tool results above."},
]


def main():
    if using_real_model():
        print("Mode: REAL model (ANTHROPIC_API_KEY is set)\n")
    else:
        print("Mode: TEST - fake model, no API calls (ANTHROPIC_API_KEY is not set)\n")

    log = ActionLog()
    agent = Agent(
        name="Demo",
        instructions=DEMO_INSTRUCTIONS,
        tools=[COUNT_ROWS_TOOL],
        log=log,
        fake_script=DEMO_FAKE_SCRIPT,
    )
    answer = agent.run(DEMO_TASK)

    print(f"\nFinal answer: {answer}")
    print(f"Full log: {log.path}")


if __name__ == "__main__":
    main()
