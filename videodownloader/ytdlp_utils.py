"""yt-dlp version checking/updating, including the pre-launch auto-update."""

import json
import os
import subprocess
import sys
import urllib.request

from videodownloader.optional_deps import yt_dlp
from videodownloader.os_utils import restart_app

# Set on the relaunched process's environment right before restart_app() so
# that if pip reports success but the version check still sees the old
# version afterward, the next launch doesn't update-and-restart forever.
_UPDATE_ATTEMPTED_ENV_VAR = "VIDEO_DOWNLOADER_YTDLP_UPDATE_ATTEMPTED"


def get_installed_ytdlp_version():
    if yt_dlp is None:
        return None
    return getattr(yt_dlp.version, "__version__", None)


def parse_version_tuple(version_str):
    parts = []
    for chunk in version_str.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def version_is_newer(candidate, current):
    if not candidate or not current:
        return False
    return parse_version_tuple(candidate) > parse_version_tuple(current)


def get_latest_ytdlp_version(timeout=4):
    """Best-effort check against PyPI. Returns None on any failure (offline, blocked, etc.)."""
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("info", {}).get("version")
    except Exception:
        return None


def update_ytdlp_package():
    """Run `pip install --upgrade yt-dlp` using the same interpreter running this app."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            text=True,
        )
        return result.returncode == 0, result.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def check_and_apply_ytdlp_update_before_launch():
    """
    Best-effort, non-blocking-in-spirit check that runs before the window
    opens (so there's no in-progress work to lose). If a newer yt-dlp is
    on PyPI, install it and relaunch this script so the update actually
    takes effect. Any failure here (offline, PyPI unreachable, pip error)
    is silent and the app just opens with whatever version is installed.
    """
    if yt_dlp is None:
        return
    current = get_installed_ytdlp_version()
    latest = get_latest_ytdlp_version()
    if not (latest and version_is_newer(latest, current)):
        return

    if os.environ.get(_UPDATE_ATTEMPTED_ENV_VAR) == latest:
        # Already tried updating to this exact version in the immediately
        # preceding launch and it didn't take (pip reported success but the
        # installed version still doesn't match) — open with what's
        # installed instead of relaunching forever.
        print(
            f"[yt-dlp] Already attempted updating to v{latest} in the previous "
            f"launch; continuing with v{current} to avoid a relaunch loop."
        )
        return

    print(f"[yt-dlp] Newer version available: {current} -> {latest}. Updating...")
    ok, output = update_ytdlp_package()
    if ok:
        print("[yt-dlp] Updated. Restarting...")
        os.environ[_UPDATE_ATTEMPTED_ENV_VAR] = latest
        restart_app()
    else:
        print("[yt-dlp] Update failed, continuing with the current version.")
        print(output)
