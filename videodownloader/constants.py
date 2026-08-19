"""Static configuration data: quality/template/cookie option maps, theme
colors, and preferred fonts. Pure literal data, no dependencies."""

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
