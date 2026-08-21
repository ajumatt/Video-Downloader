"""The main application window: VideoDownloaderApp, assembled from the
mixins in this package. Each mixin owns one cohesive group of behavior
(theme, ffmpeg, yt-dlp, queue, etc.) but they all operate on the same
`self` — the same widgets, StringVars, and shared state defined here."""

import platform
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

from videodownloader.optional_deps import yt_dlp
from videodownloader.constants import PREFERRED_UI_FONTS, PREFERRED_MONO_FONTS
from videodownloader.config import load_config

from videodownloader.gui.toast_mixin import ToastMixin
from videodownloader.gui.theme_mixin import ThemeMixin
from videodownloader.gui.ytdlp_mixin import YtdlpMixin
from videodownloader.gui.app_update_mixin import AppUpdateMixin
from videodownloader.gui.misc_mixin import MiscMixin
from videodownloader.gui.ui_builder_mixin import UIBuilderMixin
from videodownloader.gui.ffmpeg_mixin import FfmpegMixin
from videodownloader.gui.queue_mixin import QueueMixin


def maximize_window(root, system=None):
    """Best-effort: maximizes the window (title bar/taskbar stay visible,
    not true fullscreen). `system` is injectable for testing; defaults to
    the real platform. Some minimal Linux window managers don't support
    either zoomed form, so a TclError here is swallowed rather than
    crashing startup — same graceful-degradation style as the rest of
    the app's optional setup (sv-ttk/ffmpeg fallbacks)."""
    if system is None:
        system = platform.system()
    try:
        if system == "Linux":
            root.attributes("-zoomed", True)
        else:
            root.state("zoomed")
    except tk.TclError:
        pass


def pick_available_font(candidates, fallback):
    try:
        available = set(tkfont.families())
    except tk.TclError:
        return fallback
    for name in candidates:
        if name in available:
            return name
    return fallback


class VideoDownloaderApp(
    ToastMixin, ThemeMixin, YtdlpMixin, AppUpdateMixin, MiscMixin,
    UIBuilderMixin, FfmpegMixin, QueueMixin,
):
    def __init__(self, root):
        self.root = root
        self.root.title("Video Downloader")
        # 1150 is taller than the usable height on a 1080p screen once the
        # taskbar is accounted for; cap it to whatever actually fits.
        default_height = min(1150, max(950, self.root.winfo_screenheight() - 100))
        self.root.geometry(f"780x{default_height}")
        self.root.minsize(700, 950)
        # Maximized on startup so helper/hint text isn't cut off at the
        # narrower default width; un-maximizing falls back to the geometry
        # set above.
        maximize_window(self.root)

        self.ffmpeg_thread = None
        self.ytdlp_thread = None
        self.ffmpeg_path = None
        self.ffmpeg_busy = False
        self.ytdlp_busy = False
        self.app_update_busy = False

        # Download queue: a list of dicts, processed by 1-5 background
        # worker threads (see the "Concurrent downloads" setting). Items
        # stay in this list after finishing (status Done/Failed/Cancelled)
        # until removed, so the queue view doubles as a session history.
        # queue_lock protects claiming the next queued item and tracking
        # active_worker_count, since multiple worker threads touch both.
        self.download_queue = []
        self.queue_tree_iids = {}
        self.queue_lock = threading.Lock()
        self.active_worker_count = 0

        self.ui_font = pick_available_font(PREFERRED_UI_FONTS, "TkDefaultFont")
        self.mono_font = pick_available_font(PREFERRED_MONO_FONTS, "TkFixedFont")

        # Load remembered settings (theme, last folder, last quality) before
        # anything gets built, so the UI opens already reflecting them.
        self.saved_config = load_config()
        self._quality_restored = False

        self._apply_theme(self.saved_config.get("theme", "light"))
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._startup_ffmpeg_check()
        self._start_app_update_check(manual=False)

        if yt_dlp is None:
            messagebox.showerror(
                "yt-dlp not found",
                "The yt-dlp package isn't installed.\n\n"
                "Open a terminal and run:\n    pip install yt-dlp\n\n"
                "Then restart this app.",
            )
