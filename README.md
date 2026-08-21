# Video Downloader

A small desktop app that wraps [yt-dlp](https://github.com/yt-dlp/yt-dlp). Paste video URLs, queue them up, and they download automatically, one at a time, with quality, subtitle, playlist, and filename options along the way.

## Setup

You need Python 3.8+ (tkinter, used for the window, ships with the standard installer on Windows and macOS).

### Windows

Put `run_video_downloader.bat` in the same folder as `video_downloader.py` and `requirements.txt`, then double-click it. It checks for Python, installs it automatically if it's missing (via winget, or by downloading the official installer directly if winget isn't available), installs the packages in requirements.txt, then launches the app. Safe to double-click every time; it just re-checks and re-installs as needed.

Automatic Python install needs admin rights (same as the ffmpeg setup did before it moved into the app). If it fails, right-click the .bat file and choose "Run as administrator", then try again. If it still can't install Python for some reason, it'll tell you and point you to python.org, with a reminder to check "Add python.exe to PATH" on the first setup screen.

### macOS / Linux

```
pip install -r requirements.txt
```

ffmpeg is handled automatically the same way as on Windows (see below).

### About ffmpeg

ffmpeg merges separate video and audio tracks into one file, which is how yt-dlp gets you the highest resolutions (YouTube in particular splits 1080p+ into separate video-only and audio-only streams). It's also needed to convert audio to MP3.

The app keeps its own copy in a folder named `ffmpeg`, created next to `video_downloader.py`. On first run, if that folder doesn't already have ffmpeg in it, the app downloads it automatically:

- Windows: full support, downloads a portable build from gyan.dev.
- macOS: full support, downloads static builds from evermeet.cx.
- Linux: downloads a static x86_64 build from johnvansickle.com. If you're on a different architecture (ARM, etc.), the download will fail and you'll need to install ffmpeg yourself (`sudo apt install ffmpeg`) and point the app at it with "Locate ffmpeg...".

The status line above the Download button shows where things stand. While ffmpeg is being fetched, the quality dropdown automatically switches to formats that don't need it, so downloads still work in the meantime, just possibly capped around 720p depending on the site. If the automatic download ever fails (no internet on first launch, a security tool blocking it, unsupported platform), click "Download ffmpeg" to retry, or "Locate ffmpeg..." to point the app at a copy you already have.

### About yt-dlp updates

yt-dlp updates constantly as sites change how their pages work, so staying current matters more than with most tools. Every time the app launches, it checks PyPI for a newer version before the window even opens. If one's found, it installs it and restarts itself automatically so the new version is actually in use, not just downloaded. This check has a short timeout and fails silently if there's no internet or PyPI is unreachable; the app just opens normally with whatever's already installed.

There's also a "Check for updates" button in the app for checking again later without closing and reopening, useful if you leave the app running for a while. If it finds an update, it asks before restarting, since by then you might have something in progress.

### Look and feel

The app uses [sv-ttk](https://github.com/rdbende/Sun-Valley-ttk-theme) for a modern light/dark theme (the toggle button is top right). It's listed in requirements.txt, so it installs the same way as yt-dlp. If it's ever missing for some reason, the app falls back to a plain built-in theme instead of failing to start.

The window opens maximized so labels and hints don't get cut off; resize or un-maximize it like any normal window if you'd rather use less of the screen.

### Settings and history

The app remembers your theme, last download folder, quality, filename style, and playlist/subtitle/cookie choices between runs, stored in `.video_downloader_config.json` in your home folder. The first time it runs, before anything's been saved, the download folder defaults to your system Downloads folder.

Every completed download gets logged to `.video_downloader_history.csv`, also in your home folder, with the URL, filename, date/time, and save location. Click "History" in the top toolbar to see it as a sortable-looking table right in the app, or "Open CSV file" from that window to view the raw file in Excel or whatever's associated with .csv on your machine. "Clear history" deletes the log if you want to start fresh.

Neither file is anything you need to manage by hand, they're just there if you want to look, back them up, or delete them.

## Run

Windows: double-click `run_video_downloader.bat`.

macOS/Linux:
```
python video_downloader.py
```

## Using it

1. Paste the URL of a video page (YouTube, and hundreds of other sites yt-dlp supports).
2. Set the folder, quality, filename style, and any options you want (playlist, subtitles, cookies — see below).
3. Click Add to Queue, or just press Enter in the URL field. The item shows up in the Queue list and starts downloading automatically if nothing else is currently running. The URL field clears so you can immediately paste and queue the next one.
4. Repeat for as many videos as you want. They download one at a time, in the order added, so your connection doesn't get split thin across a pile of simultaneous downloads.

The Queue card shows every item's status (Queued, Downloading, Done, Failed, Cancelled) and live progress. "Cancel current" stops whichever item is actively downloading and the queue moves on to the next one. "Remove selected" drops a queued item, or offers to cancel if you select the active one. "Clear completed" clears out finished/failed/cancelled entries so the list doesn't pile up.

Files save as `<video title>.<ext>` in the folder you chose, using whatever filename style is selected (see below). The app's own `ffmpeg` folder is separate from that, it's just where the app keeps its ffmpeg copy, not where videos go.

You'll get a small notification in the corner of the app when each download finishes or fails, instead of a popup you have to dismiss for every item in a queue.

The top toolbar has four buttons: History (see above), Help (opens this README with whatever app your system has associated with .md files), the light/dark toggle, and Exit.

### Playlists

Off by default. yt-dlp downloads the whole playlist if a URL happens to include a `list=` parameter (which YouTube adds to Watch Later, mixes, and other auto-generated lists too), so leaving this unchecked means pasting a normal video link only ever gets you that one video. Check "Download entire playlist" when you actually want every video in it.

### Subtitles

Check the box and set language codes (comma-separated, e.g. `en,es`) to grab subtitles alongside the video. Prefers manually-created captions and falls back to auto-generated ones. If ffmpeg is set up, subtitles get embedded directly into the video file; otherwise they're saved as separate subtitle files next to it.

### Filenames

The Filename dropdown offers a few common patterns (Title, Title - Uploader, Uploader - Title, Date - Title) or "Custom..." to type your own [yt-dlp output template](https://github.com/yt-dlp/yt-dlp#output-template). Your choice is remembered between runs.

### Sign-in-required videos

Some videos need you to be logged in (age-restricted, unlisted, members-only). The "Sign-in required?" dropdown lets you borrow cookies from a browser already logged into the site, the same way `yt-dlp --cookies-from-browser` works. The browser needs to be closed on Windows for this to work, since it can't read the cookie database while the browser has it locked.

### Extra yt-dlp options (advanced)

For anything the app doesn't have a dedicated control for, type raw yt-dlp command-line flags into the "Extra yt-dlp options" field — e.g. `--limit-rate 500K` or `--write-comments`. It accepts the same flags as the `yt-dlp` CLI itself (quoted values work too, e.g. `--output "%(uploader)s/%(title)s.%(ext)s"`), applied on top of whatever the other fields already set; if a flag conflicts with one of those (like `--format`), the flag you typed here wins. A bad or unknown flag is caught and explained when you click "Add to Queue," not partway through a download. This field is intentionally **not** remembered between runs, so a one-off flag can't silently keep affecting later, unrelated downloads.

## Notes

- The app covers cookies, subtitles, playlists, custom filenames, and (via the "Extra yt-dlp options" field above) raw yt-dlp flags for anything else. A handful of edge-case sites may still need the yt-dlp command line directly.
- YouTube occasionally breaks one of its player clients for a few days at a time, which shows up as `HTTP Error 403: Forbidden` even on the latest yt-dlp. The app tries several player clients (default, android, tv, ios, web_safari) and automatically retries a couple of times with a cleared cache before giving up, since this specific error is often intermittent. If it still fails after that, it's very likely a current YouTube-side issue rather than something wrong with your setup, worth checking [yt-dlp's GitHub issues](https://github.com/yt-dlp/yt-dlp/issues) for the current status.
