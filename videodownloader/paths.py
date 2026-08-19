"""Filesystem paths used throughout the app.

APP_DIR must resolve to the project root (where ffmpeg/, README.md, and
run_video_downloader.bat live), not to this package's own directory. It's
derived as "one level above this file's directory", which stays correct
as long as this package is a direct child of the project root.
"""

import os
import platform

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(_PACKAGE_DIR)

FFMPEG_DIR = os.path.join(APP_DIR, "ffmpeg")
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".video_downloader_config.json")
HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".video_downloader_history.csv")
README_PATH = os.path.join(APP_DIR, "README.md")
DEFAULT_DOWNLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads")
HISTORY_FIELDS = ["url", "filename", "datetime", "location"]

FFMPEG_EXE_NAME = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
FFPROBE_EXE_NAME = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"
LOCAL_FFMPEG_PATH = os.path.join(FFMPEG_DIR, FFMPEG_EXE_NAME)
