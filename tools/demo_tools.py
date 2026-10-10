"""A demo tool used to test the agent engine in Stage 2.

It will be replaced by the real department tools from Stage 3 onward.
"""

import csv

import config


def count_rows(file_name):
    """Count the data rows (not the header) in a CSV file in data/."""
    # Only allow plain file names inside data/, so the model can never
    # make the tool read a file somewhere else on the computer.
    path = config.DATA_DIR / file_name
    if path.parent != config.DATA_DIR or not path.exists():
        raise FileNotFoundError(f"No file called '{file_name}' in data/")

    with open(path, encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))

    return {"file": file_name, "rows": len(rows) - 1}


# How the tool is presented to an agent: name, description and the inputs
# it accepts (as a JSON schema), plus the Python function that does the work.
COUNT_ROWS_TOOL = {
    "name": "count_rows",
    "description": "Count the data rows (excluding the header) in a CSV file "
                   "from the data folder, e.g. 'transactions.csv'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_name": {"type": "string", "description": "File name inside data/, e.g. 'budget.csv'"},
        },
        "required": ["file_name"],
    },
    "function": count_rows,
}
