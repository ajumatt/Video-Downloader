"""ffmpeg detection, manual location, and automatic download/extraction."""

import os
import platform
import shutil
import socket
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from tkinter import filedialog, messagebox

# urlretrieve has no timeout parameter of its own; a stalled connection
# (flaky wifi, a proxy that silently drops idle connections) would
# otherwise hang this thread forever.
_FFMPEG_DOWNLOAD_TIMEOUT_SECONDS = 30

from videodownloader.config import load_config, update_config
from videodownloader.ffmpeg_utils import check_ffmpeg, find_in_dir
from videodownloader.paths import FFMPEG_DIR, FFMPEG_EXE_NAME, FFPROBE_EXE_NAME, LOCAL_FFMPEG_PATH
from videodownloader.constants import FFMPEG_SOURCES, FFMPEG_QUALITY_MAP, NO_FFMPEG_QUALITY_MAP


class FfmpegMixin:
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

        tmp_dir = None
        try:
            os.makedirs(FFMPEG_DIR, exist_ok=True)
            tmp_dir = tempfile.mkdtemp(prefix="ffmpeg_setup_")

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
            if tmp_dir:
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

        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(_FFMPEG_DOWNLOAD_TIMEOUT_SECONDS)
        try:
            urllib.request.urlretrieve(url, archive_path, reporthook=reporthook)
        finally:
            socket.setdefaulttimeout(previous_timeout)

        extract_dir = archive_path + "_extracted"
        os.makedirs(extract_dir, exist_ok=True)
        if archive_type == "zip":
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(extract_dir)
        elif archive_type == "tar.xz":
            with tarfile.open(archive_path, mode="r:xz") as tf:
                tf.extractall(extract_dir)

        return find_in_dir(extract_dir, target_name)
