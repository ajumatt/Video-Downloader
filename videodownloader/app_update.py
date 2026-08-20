"""App self-update checking against GitHub Releases. Check-only: this
never downloads or installs anything, just reports whether a newer
tagged release exists and where to find it."""

import json
import urllib.request

REPO = "ajumatt/Video-Downloader"
RELEASES_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def get_latest_app_release(timeout=4):
    """Best-effort check against GitHub. Returns (tag_name, html_url), or
    (None, None) on any failure (offline, rate-limited, etc.)."""
    try:
        req = urllib.request.Request(RELEASES_API_URL, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("tag_name"), data.get("html_url")
    except Exception:
        return None, None
