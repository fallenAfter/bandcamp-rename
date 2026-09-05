"""Bandcamp-specific ZIP handling and filename/folder parsing."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from bandcamp_rename.sanitize import sanitize_name

# Artist - Album - 01 Track Title.ext  OR  Artist - Album - 01 - Track Title.ext
_BANDCAMP_FILENAME_RE = re.compile(
    r"^(?P<artist>.+?) - (?P<album>.+?) - (?P<track_num>\d{1,2})(?: - )?\s*(?P<title>.+)$",
    re.IGNORECASE,
)

# 01 - Track Title.ext  OR  01. Track Title.ext  OR  01 Track Title.ext
_GENERIC_FILENAME_RE = re.compile(
    r"^(?:(?:track\s*)?(?P<track_num>\d{1,2})[\s.\-_]+)(?P<title>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedFilename:
    """Metadata extracted from a track filename."""

    artist: str | None = None
    album: str | None = None
    title: str | None = None
    track_number: int | None = None


def is_bandcamp_zip(path: Path) -> bool:
    """Return True if path looks like a Bandcamp album download archive."""
    if path.suffix.lower() != ".zip":
        return False
    stem = path.stem.strip()
    return " - " in stem and not stem.startswith(".")


_FORMAT_SUFFIX_RE = re.compile(
    r"\s*\[(flac|mp3|mp3-v0|mp3-320|aac|wav|aiff|aiff-16bit|aiff-24bit|alac|vorbis)\]\s*$",
    re.IGNORECASE,
)


def _strip_format_suffix(name: str) -> str:
    """Remove Bandcamp download format markers like ' [flac]' from names."""
    return _FORMAT_SUFFIX_RE.sub("", name).strip()


def _directory_has_audio(
    directory: Path,
    audio_extensions: frozenset[str],
) -> bool:
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.lower() in audio_extensions:
            return True
    return False


def is_orphaned_bandcamp_zip(
    zip_path: Path,
    root: Path,
    *,
    audio_extensions: frozenset[str] | None = None,
) -> bool:
    """Return True when a ZIP is safe to delete after its album was organized.

    Requires that the library already contains audio under Artist/Album derived
    from the ZIP name, so never-extracted archives are preserved.
    """
    if not is_bandcamp_zip(zip_path):
        return False

    extensions = audio_extensions or frozenset(
        {".flac", ".mp3", ".m4a", ".ogg", ".wav"}
    )
    extract_dir = zip_path.parent / zip_path.stem
    if extract_dir.is_dir() and _directory_has_audio(extract_dir, extensions):
        return False

    stem = _strip_format_suffix(zip_path.stem)
    parsed = parse_bandcamp_folder(stem)
    if not parsed.artist or not parsed.album:
        return False

    organized = root / sanitize_name(parsed.artist) / sanitize_name(
        _strip_format_suffix(parsed.album)
    )
    return organized.is_dir() and _directory_has_audio(organized, extensions)


def cleanup_orphaned_zips(
    root: Path,
    *,
    dry_run: bool = False,
    audio_extensions: frozenset[str] | None = None,
) -> list[Path]:
    """Remove Bandcamp ZIPs only when matching organized album audio exists."""
    removed: list[Path] = []
    for path in sorted(root.rglob("*.zip")):
        if not is_orphaned_bandcamp_zip(
            path, root, audio_extensions=audio_extensions
        ):
            continue
        removed.append(path)
        if not dry_run:
            path.unlink()
    return removed


def extract_zip(zip_path: Path, *, destination: Path | None = None) -> Path:
    """Extract a Bandcamp ZIP archive.

    By default extracts to a sibling folder named after the archive stem.
    Skips extraction if the destination folder already exists and is non-empty.
    """
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")

    target = destination or zip_path.parent / zip_path.stem
    if target.exists() and any(target.iterdir()):
        return target

    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(target)
    return target


def parse_bandcamp_folder(name: str) -> ParsedFilename:
    """Split a Bandcamp-style folder name like 'Artist - Album'."""
    cleaned = name.strip()
    if " - " not in cleaned:
        return ParsedFilename(album=cleaned or None)

    artist, album = cleaned.rsplit(" - ", 1)
    artist = artist.strip() or None
    album = album.strip() or None
    return ParsedFilename(artist=artist, album=album)


def parse_bandcamp_filename(filename: str) -> ParsedFilename | None:
    """Parse Bandcamp-style track filenames with embedded metadata."""
    stem = Path(filename).stem.strip()
    match = _BANDCAMP_FILENAME_RE.match(stem)
    if not match:
        return None

    return ParsedFilename(
        artist=match.group("artist").strip(),
        album=match.group("album").strip(),
        track_number=int(match.group("track_num")),
        title=match.group("title").strip(),
    )


def parse_generic_filename(filename: str) -> ParsedFilename | None:
    """Parse common track filename patterns like '01 - Title' or '01. Title'."""
    stem = Path(filename).stem.strip()
    match = _GENERIC_FILENAME_RE.match(stem)
    if not match:
        return None

    return ParsedFilename(
        track_number=int(match.group("track_num")),
        title=match.group("title").strip(),
    )
