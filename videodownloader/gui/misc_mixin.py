"""Folder browsing, settings persistence, filename template, help/history
windows, and the log/status widgets."""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from videodownloader.config import update_config
from videodownloader.constants import OUTPUT_TEMPLATE_PRESETS
from videodownloader.paths import README_PATH, HISTORY_PATH
from videodownloader.os_utils import open_with_default_app
from videodownloader.history import read_history
from videodownloader.text_utils import strip_ansi


class MiscMixin:
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
        if self.active_queue_item_id is not None:
            if not messagebox.askyesno(
                "Download in progress",
                "A download is currently in progress. Exit anyway? "
                "The in-progress file will likely be left incomplete.",
            ):
                return
            self.cancel_requested = True
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
