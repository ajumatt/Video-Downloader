"""Single shared home for optional third-party imports.

yt_dlp and sv_ttk are both optional at import time (the app degrades
gracefully if either is missing); this centralizes the two try/except
blocks so every module that needs to check `yt_dlp is None` imports
from here instead of repeating the try/except.
"""

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import sv_ttk
except ImportError:
    sv_ttk = None
