"""OS-level process/file helpers not specific to any other module."""

import os
import platform
import subprocess
import sys


def open_with_default_app(path):
    """Open a file with whatever the OS has associated with it. Returns True/False."""
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(path)  # noqa: this attribute only exists on Windows
        elif system == "Darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
        return True
    except Exception:
        return False


def restart_app():
    """Relaunch this script with the same interpreter and arguments."""
    os.execv(sys.executable, [sys.executable] + sys.argv)
