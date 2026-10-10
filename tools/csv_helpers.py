"""Small helpers for reading and writing CSV files, shared by all departments."""

import csv


def read_csv(path):
    """Return the rows of a CSV file as a list of dictionaries (one per row)."""
    with open(path, encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path, rows, columns):
    """Write a list of dictionaries to a CSV file with the given columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            # Write only the listed columns, in the listed order.
            writer.writerow({column: row.get(column, "") for column in columns})
