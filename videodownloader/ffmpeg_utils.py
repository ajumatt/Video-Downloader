"""ffmpeg binary verification and archive-search helpers."""

import os
import subprocess


def check_ffmpeg(path):
    """Return True if `path` (an executable name or full path) runs as ffmpeg."""
    if not path:
        return False
    try:
        result = subprocess.run(
            [path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_in_dir(root_dir, filename):
    for dirpath, _, filenames in os.walk(root_dir):
        if filename in filenames:
            return os.path.join(dirpath, filename)
    return None
