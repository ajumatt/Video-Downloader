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

import tkinter as tk

from videodownloader.gui.main_window import VideoDownloaderApp
from videodownloader.ytdlp_utils import check_and_apply_ytdlp_update_before_launch


def main():
    check_and_apply_ytdlp_update_before_launch()

    root = tk.Tk()
    app = VideoDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
