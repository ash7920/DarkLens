"""DarkLens — auditing the web for dark patterns with LLMs."""
import sys as _sys

__version__ = "1.0.0"

# Windows consoles and PowerShell redirects often use a legacy code page that cannot show
# Greek, Polish or emoji characters from shop pages and model answers.  Never let printing a
# progress line crash a long run: characters that can't be shown are written as \u escapes.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        if (getattr(_stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
            _stream.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
