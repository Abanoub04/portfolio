"""The action log: a written record of who did what during one run.

Every agent writes to the same log, one line per action, for example:

    2026-10-10 14:03:12 | Collector | TOOL CALL   | read_file {"file_name": "transactions.csv"}

Each run of the company gets its own file in logs/, named after the time
the run started. The same lines are also printed on screen (shortened),
so you can watch the agents work.
"""

import json
from datetime import datetime
from pathlib import Path

import config

# Lines printed on screen are cut to this length to keep the screen readable.
# The log file always gets the full text.
SCREEN_WIDTH = 160


class ActionLog:
    def __init__(self, log_dir=None):
        # Default to the logs/ folder from config.py. Tests pass a temporary
        # folder instead, so they don't fill up the real logs/ folder.
        log_dir = Path(log_dir or config.LOGS_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)

        run_name = datetime.now().strftime("run_%Y%m%d_%H%M%S.log")
        self.path = log_dir / run_name

    def write(self, agent_name, action, details=""):
        """Add one line to the log: time | agent | action | details."""
        # Tool inputs and results are often dictionaries or lists.
        # json.dumps turns them into readable text.
        if not isinstance(details, str):
            details = json.dumps(details, ensure_ascii=False, default=str)

        # Keep each entry on one line, so the log is easy to scan.
        details = details.replace("\n", " ")

        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{time_now} | {agent_name:<11} | {action:<11} | {details}"

        # "a" = append: add to the end of the file, never overwrite.
        with open(self.path, "a", encoding="utf-8") as file:
            file.write(line + "\n")

        print(line[:SCREEN_WIDTH])
