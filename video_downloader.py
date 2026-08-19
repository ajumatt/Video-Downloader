#!/usr/bin/env python3
"""
Video Downloader — a simple desktop GUI around yt-dlp (https://github.com/yt-dlp/yt-dlp)

Paste a video page URL, pick a folder on your machine, hit Download.
Works with YouTube and the hundreds of other sites yt-dlp supports.

ffmpeg lives in a "ffmpeg" folder next to this script. If it's not there,
the app downloads and sets it up automatically the first time it runs
(Windows and macOS fully supported, Linux best-effort). ffmpeg is what
lets yt-dlp merge separate video/audio tracks into one file, which is
how YouTube's higher resolutions work, and it's needed for MP3 conversion.
Downloads still work while ffmpeg is being fetched, just capped lower.

Setup:
    pip install yt-dlp

Run:
    python video_downloader.py
"""

import csv
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile
import tkinter as tk
from datetime import datetime
from tkinter import font as tkfont
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

from videodownloader.paths import (
    APP_DIR,
    FFMPEG_DIR,
    CONFIG_PATH,
    HISTORY_PATH,
    README_PATH,
    DEFAULT_DOWNLOAD_FOLDER,
    HISTORY_FIELDS,
    FFMPEG_EXE_NAME,
    FFPROBE_EXE_NAME,
    LOCAL_FFMPEG_PATH,
)

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Known-good, stable download links for portable ffmpeg builds.
FFMPEG_SOURCES = {
    "Windows": {
        "ffmpeg_url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "archive_type": "zip",
    },
    "Darwin": {
        "ffmpeg_url": "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
        "ffprobe_url": "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
        "archive_type": "zip",
    },
    "Linux": {
        "ffmpeg_url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        "archive_type": "tar.xz",
    },
}

FFMPEG_QUALITY_MAP = {
    "Best available": "bestvideo*+bestaudio/best",
    "1080p or lower": "bestvideo[height<=1080]*+bestaudio/best[height<=1080]",
    "720p or lower": "bestvideo[height<=720]*+bestaudio/best[height<=720]",
    "Audio only (MP3)": "bestaudio/best",
}

NO_FFMPEG_QUALITY_MAP = {
    "Best available (single file)": "best",
    "1080p or lower (single file)": "best[height<=1080]",
    "720p or lower (single file)": "best[height<=720]",
    "Audio only (original format)": "bestaudio/best",
}

# Output filename presets. "Custom..." means "use whatever's typed into
# the template box" instead of one of these.
OUTPUT_TEMPLATE_PRESETS = {
    "Title": "%(title)s.%(ext)s",
    "Title - Uploader": "%(title)s - %(uploader)s.%(ext)s",
    "Uploader - Title": "%(uploader)s - %(title)s.%(ext)s",
    "Date - Title": "%(upload_date)s - %(title)s.%(ext)s",
    "Custom...": None,
}

# yt-dlp's cookiesfrombrowser expects the browser's internal key name.
COOKIE_BROWSER_OPTIONS = {
    "None": None,
    "Chrome": "chrome",
    "Firefox": "firefox",
    "Edge": "edge",
    "Brave": "brave",
    "Opera": "opera",
    "Vivaldi": "vivaldi",
    "Safari": "safari",
}

# Colors for the log/status widgets that sv_ttk doesn't theme automatically
# (they're plain tk widgets, not ttk). Matches sv_ttk's own light/dark palette.
THEME_COLORS = {
    "light": {"bg": "#fbfbfb", "fg": "#1a1a1a", "muted": "#5c5c5c", "border": "#d6d6d6"},
    "dark": {"bg": "#1c1c1c", "fg": "#f3f3f3", "muted": "#a3a3a3", "border": "#3a3a3a"},
}

PREFERRED_UI_FONTS = ["Segoe UI", "SF Pro Text", "Helvetica Neue", "Helvetica"]
PREFERRED_MONO_FONTS = ["Cascadia Code", "Consolas", "Menlo", "DejaVu Sans Mono"]


def pick_available_font(candidates, fallback):
    try:
        available = set(tkfont.families())
    except tk.TclError:
        return fallback
    for name in candidates:
        if name in available:
            return name
    return fallback


def strip_ansi(text):
    return ANSI_RE.sub("", text)


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def update_config(**kwargs):
    """Load, merge, and rewrite the config file with the given fields."""
    config = load_config()
    config.update(kwargs)
    save_config(config)


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
    except OSError:
        return []


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


def restart_app():
    """Relaunch this script with the same interpreter and arguments."""
    os.execv(sys.executable, [sys.executable] + sys.argv)


class VideoDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Downloader")
        self.root.geometry("780x1150")
        self.root.minsize(700, 950)

        self.ffmpeg_thread = None
        self.ytdlp_thread = None
        self.cancel_requested = False
        self.ffmpeg_path = None
        self.ffmpeg_busy = False
        self.ytdlp_busy = False

        # Download queue: a list of dicts, processed one at a time by a
        # single background worker thread. Items stay in this list after
        # finishing (status Done/Failed/Cancelled) until removed, so the
        # queue view doubles as a session history.
        self.download_queue = []
        self.queue_tree_iids = {}
        self.queue_worker_running = False
        self.active_queue_item_id = None

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

        if yt_dlp is None:
            messagebox.showerror(
                "yt-dlp not found",
                "The yt-dlp package isn't installed.\n\n"
                "Open a terminal and run:\n    pip install yt-dlp\n\n"
                "Then restart this app.",
            )

    # ------------------------------------------------------------- theme --

    def _apply_theme(self, mode):
        """mode is 'light' or 'dark'. Applies sv_ttk if available and sets
        up fonts/sizes for the plain (non-ttk) widgets that need it done
        by hand, namely the log text box."""
        self.theme_mode = mode
        colors = THEME_COLORS[mode]

        if sv_ttk is not None:
            sv_ttk.set_theme(mode)
        else:
            # Fallback for machines without sv-ttk installed: best available
            # built-in ttk theme, still themed consistently even if plainer.
            style = ttk.Style()
            if "clam" in style.theme_names():
                style.theme_use("clam")

        style = ttk.Style()
        style.configure(".", font=(self.ui_font, 10))
        style.configure("Heading.TLabel", font=(self.ui_font, 15, "bold"))
        style.configure("Muted.TLabel", foreground=colors["muted"], font=(self.ui_font, 9))
        style.configure("Section.TLabelframe.Label", font=(self.ui_font, 10, "bold"))

        # The log box is a plain tk.Text, so sv_ttk can't theme it. Keep it
        # in sync by hand whenever the theme changes.
        if hasattr(self, "log_text"):
            self.log_text.configure(
                background=colors["bg"],
                foreground=colors["fg"],
                insertbackground=colors["fg"],
                highlightbackground=colors["border"],
                highlightcolor=colors["border"],
            )

    def _toggle_theme(self):
        new_mode = "dark" if self.theme_mode == "light" else "light"
        self._apply_theme(new_mode)
        self.theme_btn.configure(text="Light mode" if new_mode == "dark" else "Dark mode")
        update_config(theme=new_mode)

    # ---------------------------------------------------------------- UI --

    def _build_ui(self):
        self._ui_fully_built = False  # guards against premature config saves mid-construction

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        # --- header -----------------------------------------------------
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Video Downloader", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Powered by yt-dlp", style="Muted.TLabel").grid(row=1, column=0, sticky="w")

        toolbar = ttk.Frame(header)
        toolbar.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(toolbar, text="History", command=self._open_history_window).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Help", command=self._open_help).pack(side="left", padx=(0, 6))
        initial_theme_label = "Light mode" if self.theme_mode == "dark" else "Dark mode"
        self.theme_btn = ttk.Button(toolbar, text=initial_theme_label, command=self._toggle_theme, width=10)
        self.theme_btn.pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Exit", command=self._on_close).pack(side="left")

        # --- download card ------------------------------------------------
        card = ttk.LabelFrame(outer, text="Download", padding=16)
        card.grid(row=1, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Video URL").grid(row=0, column=0, columnspan=2, sticky="w")
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(card, textvariable=self.url_var, font=(self.ui_font, 10))
        url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 12))
        url_entry.focus_set()
        url_entry.bind("<Return>", lambda e: self._enqueue_current())

        ttk.Label(card, text="Save to").grid(row=2, column=0, columnspan=2, sticky="w")
        folder_row = ttk.Frame(card)
        folder_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 12))
        folder_row.columnconfigure(0, weight=1)
        saved_folder = self.saved_config.get("download_folder")
        initial_folder = saved_folder if saved_folder and os.path.isdir(saved_folder) else DEFAULT_DOWNLOAD_FOLDER
        self.folder_var = tk.StringVar(value=initial_folder)
        ttk.Entry(folder_row, textvariable=self.folder_var, font=(self.ui_font, 10)).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(folder_row, text="Browse...", command=self._browse_folder).grid(row=0, column=1)

        ttk.Label(card, text="Quality").grid(row=4, column=0, columnspan=2, sticky="w")
        self.quality_var = tk.StringVar(value="Best available")
        self.quality_menu = ttk.Combobox(card, textvariable=self.quality_var, state="readonly", font=(self.ui_font, 10))
        self.quality_menu.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 14))
        self.quality_menu.bind("<<ComboboxSelected>>", lambda e: self._persist_ui_state())

        # --- filename template row ---------------------------------------
        ttk.Label(card, text="Filename").grid(row=6, column=0, columnspan=2, sticky="w")
        template_row = ttk.Frame(card)
        template_row.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(2, 14))
        template_row.columnconfigure(1, weight=1)
        saved_template_name = self.saved_config.get("output_template_name", "Title")
        self.output_template_var = tk.StringVar(
            value=saved_template_name if saved_template_name in OUTPUT_TEMPLATE_PRESETS else "Title"
        )
        template_menu = ttk.Combobox(
            template_row, textvariable=self.output_template_var, state="readonly",
            values=list(OUTPUT_TEMPLATE_PRESETS.keys()), width=16, font=(self.ui_font, 10),
        )
        template_menu.grid(row=0, column=0, padx=(0, 8))
        self.custom_template_var = tk.StringVar(value=self.saved_config.get("custom_template", "%(title)s.%(ext)s"))
        self.custom_template_entry = ttk.Entry(
            template_row, textvariable=self.custom_template_var, font=(self.mono_font, 9)
        )
        self.custom_template_entry.grid(row=0, column=1, sticky="ew")
        template_menu.bind("<<ComboboxSelected>>", self._on_template_choice_changed)
        self.custom_template_var.trace_add("write", lambda *a: self._persist_ui_state())
        self._on_template_choice_changed()

        # --- playlist / subtitles / cookies row ---------------------------
        options_row = ttk.Frame(card)
        options_row.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        self.playlist_var = tk.BooleanVar(value=self.saved_config.get("download_playlist", False))
        ttk.Checkbutton(
            options_row, text="Download entire playlist", variable=self.playlist_var,
            command=self._persist_ui_state,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.subtitles_var = tk.BooleanVar(value=self.saved_config.get("download_subtitles", False))
        sub_check = ttk.Checkbutton(
            options_row, text="Subtitles", variable=self.subtitles_var, command=self._persist_ui_state
        )
        sub_check.grid(row=1, column=0, sticky="w")
        self.subtitle_lang_var = tk.StringVar(value=self.saved_config.get("subtitle_langs", "en"))
        sub_lang_entry = ttk.Entry(options_row, textvariable=self.subtitle_lang_var, width=10, font=(self.ui_font, 9))
        sub_lang_entry.grid(row=1, column=1, sticky="w", padx=(6, 0))
        self.subtitle_lang_var.trace_add("write", lambda *a: self._persist_ui_state())
        ttk.Label(options_row, text="(language codes, comma-separated)", style="Muted.TLabel").grid(
            row=1, column=2, sticky="w", padx=(6, 0)
        )

        cookie_row = ttk.Frame(card)
        cookie_row.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        ttk.Label(cookie_row, text="Sign-in required?").pack(side="left", padx=(0, 8))
        saved_browser = self.saved_config.get("cookies_browser", "None")
        self.cookies_browser_var = tk.StringVar(
            value=saved_browser if saved_browser in COOKIE_BROWSER_OPTIONS else "None"
        )
        cookie_menu = ttk.Combobox(
            cookie_row, textvariable=self.cookies_browser_var, state="readonly",
            values=list(COOKIE_BROWSER_OPTIONS.keys()), width=12, font=(self.ui_font, 10),
        )
        cookie_menu.pack(side="left")
        cookie_menu.bind("<<ComboboxSelected>>", lambda e: self._persist_ui_state())
        ttk.Label(cookie_row, text="Use cookies from this browser (must be closed on Windows)", style="Muted.TLabel").pack(
            side="left", padx=(8, 0)
        )

        # --- action row -----------------------------------------------------
        action_row = ttk.Frame(card)
        action_row.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        self.download_btn = ttk.Button(
            action_row, text="Add to Queue", command=self._enqueue_current, style="Accent.TButton"
        )
        self.download_btn.pack(side="left", ipadx=10, ipady=2)
        self.cancel_btn = ttk.Button(
            action_row, text="Cancel current", command=self._cancel_active_item, state="disabled"
        )
        self.cancel_btn.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(card, mode="determinate", maximum=100)
        self.progress.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(14, 6))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(card, textvariable=self.status_var, style="Muted.TLabel").grid(
            row=12, column=0, columnspan=2, sticky="w"
        )

        # --- queue card -----------------------------------------------------
        queue_card = ttk.LabelFrame(outer, text="Queue", padding=(16, 12, 16, 14))
        queue_card.grid(row=2, column=0, sticky="ew", pady=(14, 14))
        queue_card.columnconfigure(0, weight=1)

        queue_header = ttk.Frame(queue_card)
        queue_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        queue_header.columnconfigure(0, weight=1)
        self.queue_count_var = tk.StringVar(value="Nothing queued yet.")
        ttk.Label(queue_header, textvariable=self.queue_count_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(queue_header, text="Remove selected", command=self._remove_selected_queue_item).grid(
            row=0, column=1, padx=(0, 6)
        )
        ttk.Button(queue_header, text="Clear completed", command=self._clear_completed_queue_items).grid(row=0, column=2)

        queue_tree_frame = ttk.Frame(queue_card)
        queue_tree_frame.grid(row=1, column=0, sticky="ew")
        queue_tree_frame.columnconfigure(0, weight=1)

        self.queue_tree = ttk.Treeview(
            queue_tree_frame, columns=("url", "status", "progress"), show="headings", height=5
        )
        self.queue_tree.heading("url", text="URL")
        self.queue_tree.heading("status", text="Status")
        self.queue_tree.heading("progress", text="Progress")
        self.queue_tree.column("url", width=380)
        self.queue_tree.column("status", width=110, stretch=False)
        self.queue_tree.column("progress", width=90, stretch=False, anchor="e")
        queue_scroll = ttk.Scrollbar(queue_tree_frame, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=queue_scroll.set)
        self.queue_tree.grid(row=0, column=0, sticky="ew")
        queue_scroll.grid(row=0, column=1, sticky="ns")

        # --- activity log card -------------------------------------------
        log_card = ttk.LabelFrame(outer, text="Activity log", padding=(16, 12, 16, 16))
        log_card.grid(row=3, column=0, sticky="nsew", pady=(0, 14))
        outer.rowconfigure(3, weight=1)
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(0, weight=1)

        log_frame = ttk.Frame(log_card)
        log_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=6,
            wrap="word",
            state="disabled",
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            font=(self.mono_font, 9),
            padx=10,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # re-apply theme now that the log box exists, so its colors match
        self._apply_theme(self.theme_mode)

        # --- system status card --------------------------------------------
        sys_card = ttk.LabelFrame(outer, text="System", padding=(16, 12, 16, 14))
        sys_card.grid(row=4, column=0, sticky="ew")
        sys_card.columnconfigure(0, weight=1)

        ffmpeg_row = ttk.Frame(sys_card)
        ffmpeg_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ffmpeg_row.columnconfigure(0, weight=1)
        self.ffmpeg_status_var = tk.StringVar(value="Checking for ffmpeg...")
        ttk.Label(ffmpeg_row, textvariable=self.ffmpeg_status_var, style="Muted.TLabel", wraplength=380).grid(
            row=0, column=0, sticky="w"
        )
        ffmpeg_btns = ttk.Frame(ffmpeg_row)
        ffmpeg_btns.grid(row=0, column=1, sticky="e")
        self.download_ffmpeg_btn = ttk.Button(
            ffmpeg_btns, text="Download ffmpeg", command=lambda: self._start_ffmpeg_download(manual=True)
        )
        self.download_ffmpeg_btn.pack(side="left", padx=(0, 6))
        ttk.Button(ffmpeg_btns, text="Locate ffmpeg...", command=self._browse_ffmpeg).pack(side="left")

        ttk.Separator(sys_card, orient="horizontal").grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ytdlp_row = ttk.Frame(sys_card)
        ytdlp_row.grid(row=2, column=0, sticky="ew")
        ytdlp_row.columnconfigure(0, weight=1)
        current_version = get_installed_ytdlp_version() or "not installed"
        self.ytdlp_status_var = tk.StringVar(value=f"yt-dlp: v{current_version}")
        ttk.Label(ytdlp_row, textvariable=self.ytdlp_status_var, style="Muted.TLabel", wraplength=380).grid(
            row=0, column=0, sticky="w"
        )
        self.check_ytdlp_btn = ttk.Button(
            ytdlp_row, text="Check for updates", command=lambda: self._start_ytdlp_check(manual=True)
        )
        self.check_ytdlp_btn.grid(row=0, column=1, sticky="e")

        self._ui_fully_built = True

    # ----------------------------------------------------------- ffmpeg --

    def _startup_ffmpeg_check(self):

        config = load_config()
        saved_path = config.get("ffmpeg_path")

        if check_ffmpeg(LOCAL_FFMPEG_PATH):
            self._set_ffmpeg_path(LOCAL_FFMPEG_PATH, persist=False, bundled=True)
            return

        on_path = shutil.which("ffmpeg")
        if on_path and check_ffmpeg(on_path):
            self._set_ffmpeg_path(on_path, persist=False)
            return

        if saved_path and check_ffmpeg(saved_path):
            self._set_ffmpeg_path(saved_path, persist=False)
            return

        self._set_ffmpeg_path(None, persist=False)
        self._log(f"ffmpeg not found. Downloading it into: {FFMPEG_DIR}")
        self._start_ffmpeg_download(manual=False)

    def _browse_ffmpeg(self):
        filetypes = [("ffmpeg executable", FFMPEG_EXE_NAME), ("All files", "*.*")]
        chosen = filedialog.askopenfilename(title="Locate ffmpeg", filetypes=filetypes)
        if not chosen:
            return
        if check_ffmpeg(chosen):
            self._set_ffmpeg_path(chosen, persist=True)
            messagebox.showinfo("ffmpeg found", "ffmpeg is set up. Higher-quality merged downloads are now available.")
        else:
            messagebox.showerror("Not a valid ffmpeg", "That file didn't run as ffmpeg. Pick the actual ffmpeg executable.")

    def _set_ffmpeg_path(self, path, persist, bundled=False):
        self.ffmpeg_path = path
        if path and bundled:
            self.ffmpeg_status_var.set("ffmpeg: ready (bundled in .\\ffmpeg)")
        elif path:
            self.ffmpeg_status_var.set(f"ffmpeg: ready ({path})")
        else:
            self.ffmpeg_status_var.set(
                'ffmpeg: not set up yet. Quality is capped until it is. Use "Download ffmpeg" or "Locate ffmpeg..." above.'
            )
        if persist:
            update_config(ffmpeg_path=path)
        self._refresh_quality_options()

    def _refresh_quality_options(self):
        quality_map = FFMPEG_QUALITY_MAP if self.ffmpeg_path else NO_FFMPEG_QUALITY_MAP
        current = self.quality_var.get()
        options = list(quality_map.keys())
        self.quality_menu.configure(values=options)

        if not self._quality_restored:
            self._quality_restored = True
            saved_quality = self.saved_config.get("quality")
            if saved_quality in options:
                self.quality_var.set(saved_quality)
                return

        if current not in options:
            self.quality_var.set(options[0])

    def _start_ffmpeg_download(self, manual):
        if self.ffmpeg_busy:
            if manual:
                messagebox.showinfo("Already working", "ffmpeg setup is already in progress.")
            return
        if self.ffmpeg_path and manual:
            if not messagebox.askyesno("ffmpeg already set up", "ffmpeg is already working. Download and replace it anyway?"):
                return

        self.ffmpeg_busy = True
        self.download_ffmpeg_btn.configure(state="disabled")
        self.ffmpeg_thread = threading.Thread(target=self._run_ffmpeg_download, args=(manual,), daemon=True)
        self.ffmpeg_thread.start()

    def _run_ffmpeg_download(self, manual):
        system = platform.system()
        source = FFMPEG_SOURCES.get(system)

        if source is None:
            msg = (
                f"Automatic ffmpeg setup isn't available for {system}. "
                'Install ffmpeg with your package manager, then click "Locate ffmpeg...".'
            )
            self.root.after(0, self._set_status, "ffmpeg: unsupported platform for auto-download.")
            self.root.after(0, self._log, msg)
            if manual:
                self.root.after(0, messagebox.showwarning, "Not supported", msg)
            self.root.after(0, self._finish_ffmpeg_download)
            return

        os.makedirs(FFMPEG_DIR, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(prefix="ffmpeg_setup_")
        try:
            self.root.after(0, self._set_status, "Downloading ffmpeg...")
            self.root.after(0, self.progress.configure, {"value": 0})

            ffmpeg_found = self._fetch_and_extract(source["ffmpeg_url"], source["archive_type"], tmp_dir, FFMPEG_EXE_NAME)
            if not ffmpeg_found:
                raise RuntimeError("Couldn't find ffmpeg inside the downloaded package.")

            if source.get("ffprobe_url"):
                ffprobe_found = self._fetch_and_extract(
                    source["ffprobe_url"], source["archive_type"], tmp_dir, FFPROBE_EXE_NAME
                )
            else:
                ffprobe_found = find_in_dir(tmp_dir, FFPROBE_EXE_NAME)

            dest_ffmpeg = os.path.join(FFMPEG_DIR, FFMPEG_EXE_NAME)
            shutil.copy2(ffmpeg_found, dest_ffmpeg)
            if system != "Windows":
                os.chmod(dest_ffmpeg, 0o755)

            if ffprobe_found:
                dest_ffprobe = os.path.join(FFMPEG_DIR, FFPROBE_EXE_NAME)
                shutil.copy2(ffprobe_found, dest_ffprobe)
                if system != "Windows":
                    os.chmod(dest_ffprobe, 0o755)

            if not check_ffmpeg(dest_ffmpeg):
                raise RuntimeError("Downloaded ffmpeg, but it didn't run correctly on this machine.")

            self.root.after(0, self._set_ffmpeg_path, dest_ffmpeg, False, True)
            self.root.after(0, self.progress.configure, {"value": 100})
            self.root.after(0, self._set_status, "ffmpeg ready.")
            self.root.after(0, self._log, f"ffmpeg set up in: {FFMPEG_DIR}")
            if manual:
                self.root.after(0, messagebox.showinfo, "ffmpeg ready", "ffmpeg is set up. Higher-quality merged downloads are now available.")

        except Exception as exc:
            msg = f"Couldn't set up ffmpeg automatically: {exc}"
            self.root.after(0, self._set_status, "ffmpeg setup failed.")
            self.root.after(0, self._log, msg)
            self.root.after(0, self.progress.configure, {"value": 0})
            if manual:
                self.root.after(0, messagebox.showerror, "ffmpeg setup failed", msg)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            self.root.after(0, self._finish_ffmpeg_download)

    def _finish_ffmpeg_download(self):
        self.ffmpeg_busy = False
        self.download_ffmpeg_btn.configure(state="normal")

    def _fetch_and_extract(self, url, archive_type, tmp_dir, target_name):
        archive_path = os.path.join(tmp_dir, f"{target_name}_download")

        def reporthook(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                pct = min(downloaded / total_size * 100, 100)
                self.root.after(0, self.progress.configure, {"value": pct})
                self.root.after(0, self._set_status, f"Downloading ffmpeg... {pct:.0f}%")

        urllib.request.urlretrieve(url, archive_path, reporthook=reporthook)

        extract_dir = archive_path + "_extracted"
        os.makedirs(extract_dir, exist_ok=True)
        if archive_type == "zip":
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(extract_dir)
        elif archive_type == "tar.xz":
            with tarfile.open(archive_path, mode="r:xz") as tf:
                tf.extractall(extract_dir)

        return find_in_dir(extract_dir, target_name)

    # ------------------------------------------------------------ yt-dlp --

    def _start_ytdlp_check(self, manual):
        if yt_dlp is None:
            if manual:
                messagebox.showerror("yt-dlp not found", "Install it first with: pip install yt-dlp")
            return
        if self.ytdlp_busy:
            if manual:
                messagebox.showinfo("Already working", "Already checking for a yt-dlp update.")
            return

        self.ytdlp_busy = True
        self.check_ytdlp_btn.configure(state="disabled")
        self.ytdlp_thread = threading.Thread(target=self._run_ytdlp_check, args=(manual,), daemon=True)
        self.ytdlp_thread.start()

    def _run_ytdlp_check(self, manual):
        current = get_installed_ytdlp_version()
        self.root.after(0, self.ytdlp_status_var.set, f"yt-dlp: v{current} (checking for updates...)")

        latest = get_latest_ytdlp_version()

        if latest is None:
            self.root.after(0, self.ytdlp_status_var.set, f"yt-dlp: v{current} (couldn't check for updates)")
            if manual:
                self.root.after(
                    0, messagebox.showwarning, "Couldn't check", "Couldn't reach PyPI to check for a newer version. Check your internet connection and try again."
                )
            self.root.after(0, self._finish_ytdlp_check)
            return

        if not version_is_newer(latest, current):
            self.root.after(0, self.ytdlp_status_var.set, f"yt-dlp: v{current} (up to date)")
            if manual:
                self.root.after(0, messagebox.showinfo, "Up to date", f"You're already on the latest version (v{current}).")
            self.root.after(0, self._finish_ytdlp_check)
            return

        self.root.after(0, self.ytdlp_status_var.set, f"yt-dlp: updating to v{latest}...")
        self.root.after(0, self._log, f"Updating yt-dlp: v{current} -> v{latest}")

        ok, output = update_ytdlp_package()

        if ok:
            self.root.after(0, self.ytdlp_status_var.set, f"yt-dlp: v{latest} installed (restart to use it)")
            self.root.after(0, self._log, f"yt-dlp updated to v{latest}. Restart the app to use it.")
            self.root.after(0, self._offer_restart, latest)
        else:
            self.root.after(0, self.ytdlp_status_var.set, f"yt-dlp: v{current} (update failed)")
            self.root.after(0, self._log, f"yt-dlp update failed: {output.strip()}")
            if manual:
                self.root.after(0, messagebox.showerror, "Update failed", f"Couldn't update yt-dlp:\n\n{output.strip()}")

        self.root.after(0, self._finish_ytdlp_check)

    def _finish_ytdlp_check(self):
        self.ytdlp_busy = False
        self.check_ytdlp_btn.configure(state="normal")

    def _offer_restart(self, new_version):
        if messagebox.askyesno(
            "Restart to finish update",
            f"yt-dlp was updated to v{new_version}. Restart the app now to use it?",
        ):
            restart_app()

    # ------------------------------------------------------------- misc --

    def _browse_folder(self):
        chosen = filedialog.askdirectory(
            title="Choose a download folder",
            initialdir=self.folder_var.get() or os.path.expanduser("~"),
        )
        if chosen:
            self.folder_var.set(chosen)
            self._persist_ui_state()

    def _persist_ui_state(self):
        if not getattr(self, "_ui_fully_built", False):
            return
        update_config(
            theme=self.theme_mode,
            download_folder=self.folder_var.get(),
            quality=self.quality_var.get(),
            output_template_name=self.output_template_var.get(),
            custom_template=self.custom_template_var.get(),
            download_playlist=self.playlist_var.get(),
            download_subtitles=self.subtitles_var.get(),
            subtitle_langs=self.subtitle_lang_var.get(),
            cookies_browser=self.cookies_browser_var.get(),
        )

    def _on_template_choice_changed(self, event=None):
        preset_name = self.output_template_var.get()
        preset_value = OUTPUT_TEMPLATE_PRESETS.get(preset_name)
        if preset_value is None:
            # "Custom..." - let the user type their own template.
            self.custom_template_entry.configure(state="normal")
        else:
            self.custom_template_var.set(preset_value)
            self.custom_template_entry.configure(state="disabled")
        self._persist_ui_state()

    def _current_output_template(self):
        preset_value = OUTPUT_TEMPLATE_PRESETS.get(self.output_template_var.get())
        return preset_value if preset_value is not None else (self.custom_template_var.get() or "%(title)s.%(ext)s")

    def _on_close(self):
        self._persist_ui_state()
        self.root.destroy()

    def _open_help(self):
        if not os.path.exists(README_PATH):
            messagebox.showinfo(
                "README not found",
                f"Couldn't find README.md next to the app.\n\nExpected it at:\n{README_PATH}",
            )
            return
        if not open_with_default_app(README_PATH):
            messagebox.showerror(
                "Couldn't open README",
                f"Couldn't open the README automatically. You can open it yourself from:\n{README_PATH}",
            )

    def _open_history_window(self):
        rows = read_history()

        win = tk.Toplevel(self.root)
        win.title("Download history")
        win.geometry("760x420")
        win.minsize(600, 320)
        win.transient(self.root)

        container = ttk.Frame(win, padding=14)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        header_row = ttk.Frame(container)
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_row.columnconfigure(0, weight=1)
        count_text = f"{len(rows)} download{'s' if len(rows) != 1 else ''} logged" if rows else "No downloads logged yet."
        ttk.Label(header_row, text=count_text, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header_row, text="Open CSV file", command=lambda: open_with_default_app(HISTORY_PATH)).grid(
            row=0, column=1, padx=(0, 6)
        )
        ttk.Button(header_row, text="Clear history", command=lambda: self._clear_history(win)).grid(row=0, column=2)

        tree_frame = ttk.Frame(container)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        columns = ("datetime", "filename", "location", "url")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        tree.heading("datetime", text="Date/time")
        tree.heading("filename", text="Filename")
        tree.heading("location", text="Location")
        tree.heading("url", text="URL")
        tree.column("datetime", width=140, stretch=False)
        tree.column("filename", width=220)
        tree.column("location", width=180)
        tree.column("url", width=200)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        for row in rows:
            tree.insert(
                "", "end",
                values=(row.get("datetime", ""), row.get("filename", ""), row.get("location", ""), row.get("url", "")),
            )

    def _clear_history(self, history_window):
        if not os.path.exists(HISTORY_PATH):
            history_window.destroy()
            return
        if messagebox.askyesno("Clear history", "Delete the download history? This can't be undone.", parent=history_window):
            try:
                os.remove(HISTORY_PATH)
            except OSError:
                pass
            history_window.destroy()
            self._open_history_window()

    def _log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", strip_ansi(message) + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, message):
        self.status_var.set(strip_ansi(message))

    # -------------------------------------------------------- download --

    def _enqueue_current(self):
        if yt_dlp is None:
            messagebox.showerror("yt-dlp not found", "Install it first with: pip install yt-dlp")
            return

        url = self.url_var.get().strip()
        folder = self.folder_var.get().strip()

        if not url:
            messagebox.showwarning("Missing URL", "Paste a video URL first.")
            return
        if not folder:
            messagebox.showwarning("Missing folder", "Choose a folder to save the video in.")
            return
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Can't use this folder", str(exc))
                return

        item = {
            "id": str(uuid.uuid4()),
            "url": url,
            "folder": folder,
            "quality": self.quality_var.get(),
            "template": self._current_output_template(),
            "playlist": self.playlist_var.get(),
            "subtitles": self.subtitles_var.get(),
            "subtitle_langs": self.subtitle_lang_var.get(),
            "cookies_browser": COOKIE_BROWSER_OPTIONS.get(self.cookies_browser_var.get()),
            "status": "Queued",
            "progress": 0,
            "error": None,
            "filename": None,
        }
        self.download_queue.append(item)
        self._insert_queue_row(item)
        self._update_queue_count_label()
        self.url_var.set("")
        self._log(f"Added to queue: {url}")
        self._maybe_start_queue_worker()

    def _cancel_active_item(self):
        self.cancel_requested = True
        self._set_status("Cancelling...")

    # ----------------------------------------------------------- queue --

    def _insert_queue_row(self, item):
        iid = self.queue_tree.insert("", "end", values=(item["url"], item["status"], self._progress_text(item)))
        self.queue_tree_iids[item["id"]] = iid

    def _update_queue_row(self, item):
        iid = self.queue_tree_iids.get(item["id"])
        if iid and self.queue_tree.exists(iid):
            self.queue_tree.item(iid, values=(item["url"], item["status"], self._progress_text(item)))

    def _progress_text(self, item):
        if item["status"] == "Downloading":
            return f"{item['progress']:.0f}%"
        if item["status"] == "Done":
            return "100%"
        return "-"

    def _update_queue_count_label(self):
        if not self.download_queue:
            self.queue_count_var.set("Nothing queued yet.")
            return
        counts = {}
        for i in self.download_queue:
            counts[i["status"]] = counts.get(i["status"], 0) + 1
        order = ["Downloading", "Queued", "Done", "Failed", "Cancelled"]
        parts = [f"{counts[status]} {status.lower()}" for status in order if counts.get(status)]
        self.queue_count_var.set(", ".join(parts))

    def _remove_selected_queue_item(self):
        selection = self.queue_tree.selection()
        if not selection:
            return
        iid = selection[0]
        item = next((i for i in self.download_queue if self.queue_tree_iids.get(i["id"]) == iid), None)
        if item is None:
            return
        if item["status"] == "Downloading":
            if messagebox.askyesno("Cancel download?", "This item is currently downloading. Cancel it?"):
                self._cancel_active_item()
            return
        self.download_queue.remove(item)
        self.queue_tree.delete(iid)
        self.queue_tree_iids.pop(item["id"], None)
        self._update_queue_count_label()

    def _clear_completed_queue_items(self):
        finished = [i for i in self.download_queue if i["status"] in ("Done", "Failed", "Cancelled")]
        for item in finished:
            iid = self.queue_tree_iids.pop(item["id"], None)
            if iid and self.queue_tree.exists(iid):
                self.queue_tree.delete(iid)
            self.download_queue.remove(item)
        self._update_queue_count_label()

    def _maybe_start_queue_worker(self):
        if not self.queue_worker_running:
            self.queue_worker_running = True
            threading.Thread(target=self._process_queue_worker, daemon=True).start()

    def _process_queue_worker(self):
        while True:
            next_item = next((i for i in self.download_queue if i["status"] == "Queued"), None)
            if next_item is None:
                break
            self._download_one_item(next_item)
        self.queue_worker_running = False
        self.root.after(0, self._on_queue_idle)

    def _on_queue_idle(self):
        self.cancel_btn.configure(state="disabled")
        self._set_status("Ready.")

    # -------------------------------------------------------- download --

    def _download_one_item(self, item):
        self.active_queue_item_id = item["id"]
        item["status"] = "Downloading"
        item["progress"] = 0
        self.cancel_requested = False

        self.root.after(0, self._update_queue_row, item)
        self.root.after(0, self._update_queue_count_label)
        self.root.after(0, self.cancel_btn.configure, {"state": "normal"})
        self.root.after(0, self.progress.configure, {"value": 0})
        self.root.after(0, self._set_status, "Starting...")
        self.root.after(0, self._log, f"Fetching: {item['url']}")

        quality_map = FFMPEG_QUALITY_MAP if self.ffmpeg_path else NO_FFMPEG_QUALITY_MAP
        fmt = quality_map.get(item["quality"], "best")

        def progress_hook(d):
            if self.cancel_requested:
                raise yt_dlp.utils.DownloadError("Cancelled by user")
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    pct = downloaded / total * 100
                    item["progress"] = pct
                    self.root.after(0, self.progress.configure, {"value": pct})
                    self.root.after(0, self._update_queue_row, item)
                    speed = d.get("_speed_str", "").strip()
                    eta = d.get("_eta_str", "").strip()
                    self.root.after(0, self._set_status, f"Downloading... {pct:.1f}%  {speed}  ETA {eta}")
            elif d["status"] == "finished":
                item["progress"] = 100
                self.root.after(0, self.progress.configure, {"value": 100})
                self.root.after(0, self._update_queue_row, item)
                self.root.after(0, self._set_status, "Processing...")
                filename = d.get("filename", "")
                item["_raw_filename"] = filename
                self.root.after(0, self._log, f"Downloaded: {os.path.basename(filename)}")

        def postprocessor_hook(d):
            # Fires after merging/audio-extraction; gives us the actual
            # final filename when it differs from the raw download (e.g.
            # merged into .mp4, or converted to .mp3).
            if d.get("status") == "finished":
                info = d.get("info_dict") or {}
                final_path = info.get("filepath") or info.get("_filename")
                if final_path:
                    item["_final_filepath"] = final_path

        ydl_opts = {
            "outtmpl": os.path.join(item["folder"], item["template"]),
            "format": fmt,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "color": "no_color",
            "noplaylist": not item["playlist"],
            # YouTube periodically breaks the default web client and fixes
            # it a few days later; trying these in order is the standard
            # workaround while that's happening, since it's usually only
            # one or two clients affected at a time.
            "extractor_args": {"youtube": {"player_client": ["default", "android", "tv", "ios", "web_safari"]}},
        }

        if item["subtitles"]:
            langs = [lang.strip() for lang in item["subtitle_langs"].split(",") if lang.strip()] or ["en"]
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitleslangs"] = langs

        if item["cookies_browser"]:
            ydl_opts["cookiesfrombrowser"] = (item["cookies_browser"],)

        if self.ffmpeg_path:
            ydl_opts["ffmpeg_location"] = self.ffmpeg_path
            if "Audio only" in item["quality"]:
                ydl_opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ]
            else:
                ydl_opts["merge_output_format"] = "mp4"
                if item["subtitles"]:
                    ydl_opts.setdefault("postprocessors", []).append({"key": "FFmpegEmbedSubtitle"})

        max_attempts = 3
        last_error = None
        success = False

        for attempt in range(1, max_attempts + 1):
            if self.cancel_requested:
                last_error = last_error or "Cancelled by user"
                break

            if attempt > 1:
                self.root.after(0, self._set_status, f"Retrying ({attempt}/{max_attempts})...")
                self.root.after(0, self._log, f"Retrying after: {last_error}")
                time.sleep(2)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    if attempt > 1:
                        # A stale cached player/format response is a common
                        # cause of a 403 that then clears up on retry.
                        try:
                            ydl.cache.remove()
                        except Exception:
                            pass
                    ydl.download([item["url"]])
                success = True
                break
            except Exception as exc:
                last_error = str(exc)
                is_403 = "403" in last_error
                if self.cancel_requested or not is_403 or attempt == max_attempts:
                    break

        if success:
            final_path = item.get("_final_filepath") or item.get("_raw_filename")
            filename = os.path.basename(final_path) if final_path else ""
            item["status"] = "Done"
            item["filename"] = filename
            item["progress"] = 100
            append_history(url=item["url"], filename=filename, location=item["folder"])
            self.root.after(0, self._set_status, "Done.")
            self.root.after(0, self._log, f"Saved to: {item['folder']}")
            self.root.after(0, self._show_toast, "Download complete", filename or item["url"], "success")
        else:
            clean = strip_ansi(last_error or "Unknown error")
            cancelled = "Cancelled by user" in clean
            item["status"] = "Cancelled" if cancelled else "Failed"
            item["error"] = clean

            if cancelled:
                self.root.after(0, self._set_status, "Cancelled.")
                self.root.after(0, self._log, "Cancelled.")
            else:
                is_403 = "403" in clean
                self.root.after(0, self._set_status, "Failed.")
                self.root.after(0, self._log, f"Error: {clean}")
                if is_403:
                    self.root.after(
                        0, self._log,
                        "This looks like a YouTube-side block currently affecting yt-dlp broadly, "
                        "not a problem with this app or your setup. It often clears up within a "
                        "retry or two, or with the next yt-dlp release.",
                    )
                self.root.after(0, self._show_toast, "Download failed", clean[:140], "error")

        self.root.after(0, self._update_queue_row, item)
        self.root.after(0, self._update_queue_count_label)
        self.cancel_requested = False
        self.active_queue_item_id = None

    # --------------------------------------------------------- toasts --

    def _show_toast(self, title, message, kind="info"):
        try:
            self.root.update_idletasks()
            colors = THEME_COLORS[self.theme_mode]
            accent = {"success": "#2ea043", "error": "#e5484d"}.get(kind, colors["fg"])

            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)

            frame = tk.Frame(toast, bg=colors["bg"], highlightbackground=accent, highlightthickness=2, bd=0)
            frame.pack(fill="both", expand=True)
            tk.Label(
                frame, text=title, bg=colors["bg"], fg=accent, font=(self.ui_font, 10, "bold"),
                anchor="w",
            ).pack(fill="x", padx=14, pady=(10, 2))
            tk.Label(
                frame, text=message, bg=colors["bg"], fg=colors["fg"], font=(self.ui_font, 9),
                anchor="w", justify="left", wraplength=300,
            ).pack(fill="x", padx=14, pady=(0, 10))

            toast.update_idletasks()
            w, h = toast.winfo_width(), toast.winfo_height()
            x = self.root.winfo_x() + self.root.winfo_width() - w - 24
            y = self.root.winfo_y() + self.root.winfo_height() - h - 24
            toast.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

            toast.bind("<Button-1>", lambda e: toast.destroy())
            toast.after(4500, lambda: toast.destroy() if toast.winfo_exists() else None)
        except tk.TclError:
            pass  # main window may already be closing


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
    if latest and version_is_newer(latest, current):
        print(f"[yt-dlp] Newer version available: {current} -> {latest}. Updating...")
        ok, output = update_ytdlp_package()
        if ok:
            print("[yt-dlp] Updated. Restarting...")
            restart_app()
        else:
            print("[yt-dlp] Update failed, continuing with the current version.")
            print(output)


def main():
    check_and_apply_ytdlp_update_before_launch()

    root = tk.Tk()
    app = VideoDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
