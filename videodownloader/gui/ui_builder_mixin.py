"""Builds the entire main window widget tree."""

import os
import tkinter as tk
from tkinter import ttk

from videodownloader import __version__
from videodownloader.paths import DEFAULT_DOWNLOAD_FOLDER
from videodownloader.constants import OUTPUT_TEMPLATE_PRESETS, COOKIE_BROWSER_OPTIONS
from videodownloader.ytdlp_utils import get_installed_ytdlp_version


class UIBuilderMixin:
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
        card = ttk.LabelFrame(outer, text="Download", padding=(16, 12, 16, 14), style="Section.TLabelframe")
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
        quality_row = ttk.Frame(card)
        quality_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 14))
        quality_row.columnconfigure(0, weight=1)
        self.quality_var = tk.StringVar(value="Best available")
        self.quality_menu = ttk.Combobox(
            quality_row, textvariable=self.quality_var, state="readonly", font=(self.ui_font, 10)
        )
        self.quality_menu.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.quality_menu.bind("<<ComboboxSelected>>", lambda e: self._persist_ui_state())
        ttk.Button(quality_row, text="Choose format...", command=self._open_format_picker_window).grid(
            row=0, column=1
        )

        # Separates the required path (URL/folder/quality, above) from the
        # optional/advanced settings below, so the primary flow scans faster.
        ttk.Separator(card, orient="horizontal").grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        # --- filename template row ---------------------------------------
        ttk.Label(card, text="Filename", style="Muted.TLabel").grid(row=7, column=0, columnspan=2, sticky="w")
        template_row = ttk.Frame(card)
        template_row.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(2, 14))
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
        options_row.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        self.playlist_var = tk.BooleanVar(value=self.saved_config.get("download_playlist", False))
        ttk.Checkbutton(
            options_row, text="Download entire playlist", variable=self.playlist_var,
            command=self._persist_ui_state,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            options_row, text="(applies when the URL includes YouTube's list= parameter)", style="Muted.TLabel"
        ).grid(row=0, column=1, sticky="w", padx=(6, 0), pady=(0, 6))

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

        self.sponsorblock_var = tk.BooleanVar(value=self.saved_config.get("download_sponsorblock", False))
        self.sponsorblock_check = ttk.Checkbutton(
            options_row, text="Remove sponsor segments (SponsorBlock)",
            variable=self.sponsorblock_var, command=self._persist_ui_state,
        )
        self.sponsorblock_check.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.sponsorblock_categories_var = tk.StringVar(
            value=self.saved_config.get("sponsorblock_categories", "sponsor,selfpromo,interaction")
        )
        self.sponsorblock_entry = ttk.Entry(
            options_row, textvariable=self.sponsorblock_categories_var, width=28, font=(self.ui_font, 9)
        )
        self.sponsorblock_entry.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        self.sponsorblock_categories_var.trace_add("write", lambda *a: self._persist_ui_state())
        ttk.Label(
            options_row,
            text="(needs ffmpeg; categories: sponsor, intro, outro, selfpromo, preview, filler, interaction, music_offtopic, hook)",
            style="Muted.TLabel",
        ).grid(row=2, column=2, sticky="w", padx=(6, 0), pady=(6, 0))

        cookie_row = ttk.Frame(card)
        cookie_row.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 4))
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
        ttk.Label(
            cookie_row,
            text="(browser must be closed first, or you'll get a database-locked error)",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))

        # --- action row -----------------------------------------------------
        action_row = ttk.Frame(card)
        action_row.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        self.download_btn = ttk.Button(
            action_row, text="Add to Queue", command=self._enqueue_current, style="Accent.TButton"
        )
        self.download_btn.pack(side="left", ipadx=10, ipady=2)
        ttk.Button(action_row, text="Add multiple...", command=self._open_batch_add_window).pack(
            side="left", padx=(8, 0)
        )

        self.progress = ttk.Progressbar(card, mode="determinate", maximum=100)
        self.progress.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(14, 6))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(card, textvariable=self.status_var, style="Muted.TLabel").grid(
            row=13, column=0, columnspan=2, sticky="w"
        )

        # --- queue card -----------------------------------------------------
        queue_card = ttk.LabelFrame(outer, text="Queue", padding=(16, 12, 16, 14), style="Section.TLabelframe")
        queue_card.grid(row=2, column=0, sticky="ew", pady=(14, 14))
        queue_card.columnconfigure(0, weight=1)

        queue_header = ttk.Frame(queue_card)
        queue_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        queue_header.columnconfigure(0, weight=1)
        self.queue_count_var = tk.StringVar(value="Nothing queued yet.")
        ttk.Label(queue_header, textvariable=self.queue_count_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        ttk.Label(queue_header, text="Concurrent downloads:", style="Muted.TLabel").grid(
            row=0, column=1, padx=(0, 4)
        )
        saved_concurrency = str(self.saved_config.get("max_concurrent_downloads", "1"))
        self.max_concurrent_var = tk.StringVar(
            value=saved_concurrency if saved_concurrency in ("1", "2", "3", "4", "5") else "1"
        )
        concurrency_menu = ttk.Combobox(
            queue_header, textvariable=self.max_concurrent_var, state="readonly",
            values=["1", "2", "3", "4", "5"], width=3,
        )
        concurrency_menu.grid(row=0, column=2, padx=(0, 6))
        concurrency_menu.bind("<<ComboboxSelected>>", lambda e: self._persist_ui_state())

        ttk.Button(queue_header, text="Remove selected", command=self._remove_selected_queue_item).grid(
            row=0, column=3, padx=(0, 6)
        )
        ttk.Button(queue_header, text="Clear completed", command=self._clear_completed_queue_items).grid(row=0, column=4)

        queue_tree_frame = ttk.Frame(queue_card)
        queue_tree_frame.grid(row=1, column=0, sticky="ew")
        queue_tree_frame.columnconfigure(0, weight=1)

        self.queue_tree = ttk.Treeview(
            queue_tree_frame, columns=("url", "status", "progress"), show="headings", height=7
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
        log_card = ttk.LabelFrame(outer, text="Activity log", padding=(16, 12, 16, 14), style="Section.TLabelframe")
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
        sys_card = ttk.LabelFrame(outer, text="System", padding=(16, 12, 16, 14), style="Section.TLabelframe")
        sys_card.grid(row=4, column=0, sticky="ew")
        sys_card.columnconfigure(0, weight=1)

        ffmpeg_row = ttk.Frame(sys_card)
        ffmpeg_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ffmpeg_row.columnconfigure(0, weight=1)
        self.ffmpeg_status_var = tk.StringVar(value="Checking for ffmpeg...")
        self.ffmpeg_status_label = ttk.Label(
            ffmpeg_row, textvariable=self.ffmpeg_status_var, style="Muted.TLabel", wraplength=380
        )
        self.ffmpeg_status_label.grid(row=0, column=0, sticky="w")
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
        self.ytdlp_status_label = ttk.Label(
            ytdlp_row, textvariable=self.ytdlp_status_var, style="Muted.TLabel", wraplength=380
        )
        self.ytdlp_status_label.grid(row=0, column=0, sticky="w")
        self.check_ytdlp_btn = ttk.Button(
            ytdlp_row, text="Check for updates", command=lambda: self._start_ytdlp_check(manual=True)
        )
        self.check_ytdlp_btn.grid(row=0, column=1, sticky="e")

        ttk.Separator(sys_card, orient="horizontal").grid(row=3, column=0, sticky="ew", pady=(8, 8))

        app_row = ttk.Frame(sys_card)
        app_row.grid(row=4, column=0, sticky="ew")
        app_row.columnconfigure(0, weight=1)
        self.app_update_status_var = tk.StringVar(value=f"App: v{__version__}")
        self.app_update_status_label = ttk.Label(
            app_row, textvariable=self.app_update_status_var, style="Muted.TLabel", wraplength=380
        )
        self.app_update_status_label.grid(row=0, column=0, sticky="w")
        app_btns = ttk.Frame(app_row)
        app_btns.grid(row=0, column=1, sticky="e")
        self.view_release_btn = ttk.Button(
            app_btns, text="View release", command=self._open_latest_release_page, state="disabled"
        )
        self.view_release_btn.pack(side="left", padx=(0, 6))
        self.check_app_update_btn = ttk.Button(
            app_btns, text="Check for updates", command=lambda: self._start_app_update_check(manual=True)
        )
        self.check_app_update_btn.pack(side="left")

        # Let the status labels above rewrap to the window's actual width on
        # resize instead of staying fixed at their initial 380px.
        self.root.bind("<Configure>", self._on_root_resize)

        self._ui_fully_built = True

    def _on_root_resize(self, event):
        if event.widget is not self.root:
            return
        new_wrap = max(280, event.width - 400)
        self.ffmpeg_status_label.configure(wraplength=new_wrap)
        self.ytdlp_status_label.configure(wraplength=new_wrap)
        self.app_update_status_label.configure(wraplength=new_wrap)
