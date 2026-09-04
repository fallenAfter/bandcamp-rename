"""Filesystem-safe name sanitization for Plex folder and file paths."""

from __future__ import annotations

import re
import unicodedata

# Characters illegal on Windows and problematic on most filesystems.
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")


def sanitize_name(name: str, *, replacement: str = "_") -> str:
    """Return a filesystem-safe name suitable for Plex artist/album/track paths.

    - Replaces invalid path characters
    - Collapses whitespace
    - Strips leading/trailing dots and spaces (Windows-safe)
    - Normalizes Unicode to NFC
    """
    if not name:
        return "Unknown"

    text = unicodedata.normalize("NFC", name)
    text = _INVALID_CHARS.sub(replacement, text)
    text = _WHITESPACE.sub(" ", text).strip(" .")
    return text or "Unknown"


def sanitize_filename(name: str, *, replacement: str = "_") -> str:
    """Sanitize a filename stem (without extension)."""
    return sanitize_name(name, replacement=replacement)
