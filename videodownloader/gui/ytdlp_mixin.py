"""Manual "Check for updates" flow for yt-dlp."""

import threading
from tkinter import messagebox

from videodownloader.optional_deps import yt_dlp
from videodownloader.os_utils import restart_app
from videodownloader.ytdlp_utils import (
    get_installed_ytdlp_version,
    get_latest_ytdlp_version,
    version_is_newer,
    update_ytdlp_package,
)


class YtdlpMixin:
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
