"""Small text helpers shared by the GUI and download logic."""

import re

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text):
    return ANSI_RE.sub("", text)
