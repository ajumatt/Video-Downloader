"""The download queue: enqueueing, the worker thread, and the actual
yt-dlp invocation for a single item."""

import os
import threading
import time
import uuid
import tkinter as tk
from tkinter import ttk, messagebox

from videodownloader.optional_deps import yt_dlp
from videodownloader.constants import COOKIE_BROWSER_OPTIONS, FFMPEG_QUALITY_MAP, NO_FFMPEG_QUALITY_MAP
from videodownloader.history import append_history
from videodownloader.text_utils import strip_ansi

# (substring to look for in a raw yt-dlp error, plain-English follow-up
# line). First match wins; checked in order, so put more specific
# markers before more general ones.
FRIENDLY_ERROR_HINTS = [
    (
        "403",
        "This looks like a YouTube-side block currently affecting yt-dlp broadly, "
        "not a problem with this app or your setup. It often clears up within a "
        "retry or two, or with the next yt-dlp release.",
    ),
    (
        "Unsupported URL",
        "This doesn't look like a page yt-dlp recognizes. Double-check it's a "
        "direct link to a video page.",
    ),
    (
        "Private video",
        "This video is private and can't be downloaded without access to the "
        "account it belongs to.",
    ),
    (
        "Video unavailable",
        "This video isn't available anymore (removed, region-blocked, or "
        'age-restricted). If it\'s age-restricted, try the "Sign-in required?" option.',
    ),
    ("Name or service not known", "Couldn't reach the internet. Check your connection and try again."),
    ("getaddrinfo failed", "Couldn't reach the internet. Check your connection and try again."),
    ("Failed to establish a new connection", "Couldn't reach the internet. Check your connection and try again."),
    ("timed out", "The connection timed out. Check your internet connection and try again."),
]


def _friendly_error_hint(error_text):
    for marker, hint in FRIENDLY_ERROR_HINTS:
        if marker in error_text:
            return hint
    return None


def _resolves_within_folder(folder, template):
    """True if joining `folder` with the (unsubstituted) template stays
    within `folder`. Checked against the actual joined+normalized path
    rather than pattern-matching the template string, since os.path.join
    has surprising escape cases on Windows: os.path.isabs("/etc/x") is
    False there (no drive letter = "drive-relative", not absolute), yet
    os.path.join(folder, "/etc/x") resolves to the *root of folder's
    drive*, silently escaping the chosen folder. Subfolders (e.g.
    "%(uploader)s/%(title)s.%(ext)s") are fine and intentional."""
    folder_abs = os.path.normpath(os.path.abspath(folder))
    joined_abs = os.path.normpath(os.path.abspath(os.path.join(folder, template)))
    return joined_abs == folder_abs or joined_abs.startswith(folder_abs + os.sep)


class QueueMixin:
    def _current_form_settings(self):
        """Snapshot of the form fields that apply to any newly queued item,
        whether it's added one at a time or as part of a batch."""
        sponsorblock_categories = []
        if self.ffmpeg_path and self.sponsorblock_var.get():
            sponsorblock_categories = [
                c.strip() for c in self.sponsorblock_categories_var.get().split(",") if c.strip()
            ]
        return {
            "folder": self.folder_var.get().strip(),
            "template": self._current_output_template(),
            "quality": self.quality_var.get(),
            "playlist": self.playlist_var.get(),
            "subtitles": self.subtitles_var.get(),
            "subtitle_langs": self.subtitle_lang_var.get(),
            "cookies_browser": COOKIE_BROWSER_OPTIONS.get(self.cookies_browser_var.get()),
            "sponsorblock_categories": sponsorblock_categories,
        }

    def _make_queue_item(self, url, settings):
        return {
            "id": str(uuid.uuid4()),
            "url": url,
            "folder": settings["folder"],
            "quality": settings["quality"],
            "template": settings["template"],
            "playlist": settings["playlist"],
            "subtitles": settings["subtitles"],
            "subtitle_langs": settings["subtitle_langs"],
            "cookies_browser": settings["cookies_browser"],
            "sponsorblock_categories": settings["sponsorblock_categories"],
            "status": "Queued",
            "progress": 0,
            "error": None,
            "filename": None,
        }

    def _validate_form_settings(self, settings):
        """Returns an error message if the current folder/template combo is
        unusable, or None if it's fine. Also creates the folder if it's
        valid but doesn't exist yet. Shared by single-add and batch-add so
        the checks stay in exactly one place."""
        folder = settings["folder"]
        template = settings["template"]
        if not folder:
            return "Choose a folder to save the video in."
        if not _resolves_within_folder(folder, template):
            return (
                "The filename template can't be an absolute path or use '..' to leave "
                "the download folder. Fix it in the Filename field before adding to the queue."
            )
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as exc:
                return str(exc)
        return None

    def _enqueue_current(self):
        if yt_dlp is None:
            messagebox.showerror("yt-dlp not found", "Install it first with: pip install yt-dlp")
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a video URL first.")
            return

        settings = self._current_form_settings()
        error = self._validate_form_settings(settings)
        if error:
            messagebox.showwarning("Can't add to queue", error)
            return

        item = self._make_queue_item(url, settings)
        self.download_queue.append(item)
        self._insert_queue_row(item)
        self._update_queue_count_label()
        self.url_var.set("")
        self._log(f"Added to queue: {url}")
        self._maybe_start_queue_worker()

    def _open_batch_add_window(self):
        if yt_dlp is None:
            messagebox.showerror("yt-dlp not found", "Install it first with: pip install yt-dlp")
            return

        win = tk.Toplevel(self.root)
        win.title("Add Multiple URLs")
        win.geometry("520x420")
        win.minsize(420, 300)
        win.transient(self.root)

        container = ttk.Frame(win, padding=14)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        ttk.Label(container, text="Paste one URL per line:").grid(row=0, column=0, sticky="w", pady=(0, 6))

        text_frame = ttk.Frame(container)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        url_text = tk.Text(text_frame, wrap="word", font=(self.ui_font, 10))
        url_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=url_text.yview)
        url_text.configure(yscrollcommand=url_scroll.set)
        url_text.grid(row=0, column=0, sticky="nsew")
        url_scroll.grid(row=0, column=1, sticky="ns")
        url_text.focus_set()

        button_row = ttk.Frame(container)
        button_row.grid(row=2, column=0, sticky="e", pady=(10, 0))

        def submit():
            raw_lines = url_text.get("1.0", "end").splitlines()
            self._enqueue_batch(raw_lines)
            win.destroy()

        ttk.Button(button_row, text="Cancel", command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(button_row, text="Add All", command=submit, style="Accent.TButton").pack(side="left")

    def _enqueue_batch(self, raw_lines):
        settings = self._current_form_settings()
        error = self._validate_form_settings(settings)
        if error:
            messagebox.showwarning("Can't add to queue", error)
            return

        already_queued = {i["url"] for i in self.download_queue}
        seen = set()
        added = 0
        duplicates = 0
        invalid = 0

        for raw_line in raw_lines:
            url = raw_line.strip()
            if not url:
                continue
            if not (url.startswith("http://") or url.startswith("https://")):
                invalid += 1
                continue
            if url in already_queued or url in seen:
                duplicates += 1
                continue
            seen.add(url)
            item = self._make_queue_item(url, settings)
            self.download_queue.append(item)
            self._insert_queue_row(item)
            added += 1

        if added:
            self._update_queue_count_label()
            self._maybe_start_queue_worker()

        summary = f"Added {added} to queue"
        details = []
        if duplicates:
            details.append(f"{duplicates} duplicate{'s' if duplicates != 1 else ''} skipped")
        if invalid:
            details.append(f"{invalid} invalid line{'s' if invalid != 1 else ''} skipped")
        if details:
            summary += f" ({', '.join(details)})"
        summary += "."
        self._log(summary)

    def _cancel_active_item(self):
        self.cancel_requested = True
        self._set_status("Cancelling...")

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
            # merged into .mp4, or converted to .mp3). Also re-checked here
            # so cancelling during a merge/extraction isn't ignored (only
            # progress_hook's "downloading" phase used to check this).
            if self.cancel_requested:
                raise yt_dlp.utils.DownloadError("Cancelled by user")
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

            if item["sponsorblock_categories"]:
                # Mirrors yt-dlp's own --sponsorblock-remove: SponsorBlock
                # fetches the segments, ModifyChapters cuts them out.
                ydl_opts.setdefault("postprocessors", []).append(
                    {"key": "SponsorBlock", "categories": item["sponsorblock_categories"]}
                )
                ydl_opts.setdefault("postprocessors", []).append(
                    {"key": "ModifyChapters", "remove_sponsor_segments": item["sponsorblock_categories"]}
                )

        max_attempts = 3
        last_error = None
        success = False
        was_cancelled = False

        for attempt in range(1, max_attempts + 1):
            if self.cancel_requested:
                was_cancelled = True
                last_error = last_error or "Cancelled by user"
                break

            if attempt > 1:
                self.root.after(0, self._set_status, f"Retrying ({attempt}/{max_attempts})...")
                self.root.after(0, self._log, f"Retrying after: {last_error}")
                time.sleep(2)
                if self.cancel_requested:
                    was_cancelled = True
                    break

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
                if self.cancel_requested:
                    was_cancelled = True
                    break
                is_403 = "403" in last_error
                if not is_403 or attempt == max_attempts:
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
            cancelled = was_cancelled or "Cancelled by user" in clean
            item["status"] = "Cancelled" if cancelled else "Failed"
            item["error"] = clean

            if cancelled:
                self.root.after(0, self._set_status, "Cancelled.")
                self.root.after(0, self._log, "Cancelled.")
            else:
                self.root.after(0, self._set_status, "Failed.")
                self.root.after(0, self._log, f"Error: {clean}")
                hint = _friendly_error_hint(clean)
                if hint:
                    self.root.after(0, self._log, hint)
                self.root.after(0, self._show_toast, "Download failed", clean[:140], "error")

        self.root.after(0, self._update_queue_row, item)
        self.root.after(0, self._update_queue_count_label)
        self.cancel_requested = False
        self.active_queue_item_id = None
