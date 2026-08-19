"""Download history log, kept as a CSV file in the user's home folder."""

import csv
import os
from datetime import datetime

from videodownloader.paths import HISTORY_PATH, HISTORY_FIELDS


def ensure_history_file():
    if not os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=HISTORY_FIELDS).writeheader()
        except OSError:
            pass


def append_history(url, filename, location):
    ensure_history_file()
    row = {
        "url": url,
        "filename": filename or "",
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "location": location,
    }
    try:
        with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=HISTORY_FIELDS).writerow(row)
    except OSError:
        pass


def read_history():
    """Returns rows newest-first, or [] if there's no history yet."""
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows.reverse()
        return rows
    except (OSError, ValueError, csv.Error):
        # ValueError covers UnicodeDecodeError from a corrupted/mis-encoded
        # file; csv.Error covers things like a stray NUL byte mid-file.
        return []
