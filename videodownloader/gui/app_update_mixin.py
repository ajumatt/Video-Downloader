"""Check-only "is there a newer app release?" flow: a best-effort check
on startup plus a manual "Check for updates" button, mirroring the
yt-dlp check's shape but never auto-installing -- there's no reliable
way to self-replace the running app across both the git-clone and
portable-zip distribution paths, so this only notifies and links to
the GitHub release page for the user to download deliberately."""

import threading
import webbrowser
from tkinter import messagebox

from videodownloader import __version__
from videodownloader.app_update import get_latest_app_release
from videodownloader.ytdlp_utils import version_is_newer


class AppUpdateMixin:
    def _start_app_update_check(self, manual):
        if self.app_update_busy:
            if manual:
                messagebox.showinfo("Already working", "Already checking for an app update.")
            return

        self.app_update_busy = True
        self.check_app_update_btn.configure(state="disabled")
        threading.Thread(target=self._run_app_update_check, args=(manual,), daemon=True).start()

    def _run_app_update_check(self, manual):
        latest_tag, release_url = get_latest_app_release()

        if latest_tag is None:
            self.root.after(0, self.app_update_status_var.set, f"App: v{__version__} (couldn't check for updates)")
            if manual:
                self.root.after(
                    0, messagebox.showwarning, "Couldn't check",
                    "Couldn't reach GitHub to check for a newer version. Check your internet connection and try again.",
                )
            self.root.after(0, self._finish_app_update_check)
            return

        if not version_is_newer(latest_tag, __version__):
            self.root.after(0, self.app_update_status_var.set, f"App: v{__version__} (up to date)")
            if manual:
                self.root.after(0, messagebox.showinfo, "Up to date", f"You're already on the latest version (v{__version__}).")
            self.root.after(0, self._finish_app_update_check)
            return

        self._latest_release_url = release_url
        self.root.after(0, self.app_update_status_var.set, f"App: v{__version__} ({latest_tag} available)")
        self.root.after(0, self.view_release_btn.configure, {"state": "normal"})
        if manual:
            self.root.after(
                0, messagebox.showinfo, "Update available",
                f'{latest_tag} is available. Click "View release" to download it.',
            )
        self.root.after(0, self._finish_app_update_check)

    def _finish_app_update_check(self):
        self.app_update_busy = False
        self.check_app_update_btn.configure(state="normal")

    def _open_latest_release_page(self):
        url = getattr(self, "_latest_release_url", None)
        if url:
            webbrowser.open(url)
