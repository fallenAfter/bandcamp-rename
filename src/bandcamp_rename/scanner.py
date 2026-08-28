"""Directory scanning for audio files, Bandcamp ZIPs, and companion files."""

from __future__ import annotations

from pathlib import Path

from bandcamp_rename.models import ScanResult

DEFAULT_AUDIO_EXTENSIONS = frozenset({".flac", ".mp3", ".m4a", ".ogg", ".wav"})
DEFAULT_SKIP_FILENAMES = frozenset({"cover.jpg", "folder.jpg", ".ds_store"})


def _normalize_extension(ext: str) -> str:
    normalized = ext.lower()
    return normalized if normalized.startswith(".") else f".{normalized}"


def _normalize_skip_name(name: str) -> str:
    return name.lower()


def is_audio_file(path: Path, extensions: frozenset[str] = DEFAULT_AUDIO_EXTENSIONS) -> bool:
    """Return True if path has a supported audio extension."""
    return path.suffix.lower() in extensions


def is_companion_file(path: Path, skip_names: frozenset[str] = DEFAULT_SKIP_FILENAMES) -> bool:
    """Return True if path is a known non-audio companion file."""
    return path.name.lower() in skip_names


def scan_directory(
    root: Path,
    *,
    extensions: frozenset[str] | None = None,
    skip_names: frozenset[str] | None = None,
) -> ScanResult:
    """Recursively scan a directory tree for audio, ZIP, and companion files."""
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    audio_exts = extensions or DEFAULT_AUDIO_EXTENSIONS
    skip = skip_names or DEFAULT_SKIP_FILENAMES
    normalized_exts = frozenset(_normalize_extension(ext) for ext in audio_exts)
    normalized_skip = frozenset(_normalize_skip_name(name) for name in skip)

    result = ScanResult(root=root.resolve())

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()
        if suffix == ".zip":
            result.zip_files.append(path)
        elif suffix in normalized_exts:
            result.audio_files.append(path)
        elif path.name.lower() in normalized_skip:
            result.companion_files.append(path)

    return result
