#!/usr/bin/env python3
"""Recover audio stranded as .bc-rename-*.tmp files after an interrupted fix.

Usage on the server:
  cd ~/bandcamp-rename
  git pull
  uv run python recover_bc_temps.py /Media/music --dry-run
  uv run python recover_bc_temps.py /Media/music
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, ID3NoHeaderError

from bandcamp_rename.sanitize import sanitize_filename

_MAGIC_EXT = (
    (b"fLaC", ".flac"),
    (b"OggS", ".ogg"),
)


def first_text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    text = str(value).strip()
    return text or None


def parse_int(value: object | None) -> int | None:
    text = first_text(value)
    if not text:
        return None
    primary = text.split("/", 1)[0].strip()
    digits = "".join(ch for ch in primary if ch.isdigit())
    return int(digits) if digits else None


def sniff_extension(path: Path) -> str:
    """Guess audio extension from file header when the temp has .tmp suffix."""
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return ".flac"
    for magic, ext in _MAGIC_EXT:
        if header.startswith(magic):
            return ext
    if header[4:8] == b"ftyp":
        return ".m4a"
    if header.startswith(b"ID3") or header[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    return ".flac"


def read_meta(path: Path) -> tuple[int | None, int | None, str | None]:
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None
    if audio is not None:
        return (
            parse_int(audio.get("tracknumber")),
            parse_int(audio.get("discnumber")),
            first_text(audio.get("title")),
        )

    # Mutagen can miss tag-only MP3s when the extension is .tmp.
    try:
        id3 = ID3(path)
    except (ID3NoHeaderError, Exception):
        return None, None, None
    return parse_int(id3.get("TRCK")), parse_int(id3.get("TPOS")), first_text(id3.get("TIT2"))


def unique_path(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem, suffix = destination.stem, destination.suffix
    index = 2
    while True:
        candidate = destination.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def plex_filename(*, track: int, disc: int | None, title: str, ext: str) -> str:
    """Match bandcamp_rename.plex_rules default templates."""
    if disc is not None and disc > 1:
        stem = f"{disc}{track:02d} - {title}"
    else:
        stem = f"{track:02d} - {title}"
    return f"{stem}{ext}"


def recover(root: Path, *, dry_run: bool) -> int:
    temps = sorted(root.rglob(".bc-rename-*.tmp"))
    print(f"Found {len(temps)} temp file(s) under {root}")
    fallback_by_dir: dict[Path, int] = defaultdict(int)
    recovered = 0
    for temp in temps:
        track_num, disc_num, title = read_meta(temp)
        ext = sniff_extension(temp)

        if track_num is not None:
            number = track_num
        else:
            fallback_by_dir[temp.parent] += 1
            number = fallback_by_dir[temp.parent]
            print(f"warning: no tracknumber tag in {temp}; using {number:02d}", file=sys.stderr)

        if title:
            safe_title = sanitize_filename(title)
        else:
            safe_title = f"Recovered Track {number}"
            print(f"warning: no title tag in {temp}", file=sys.stderr)

        filename = plex_filename(track=number, disc=disc_num, title=safe_title, ext=ext)
        destination = unique_path(temp.parent / filename)
        size_mb = temp.stat().st_size / (1024 * 1024)
        prefix = "[dry-run] " if dry_run else ""
        print(f"{prefix}{temp.name} ({size_mb:.1f} MiB) -> {destination.name}")
        if not dry_run:
            temp.rename(destination)
        recovered += 1
    return recovered


def main() -> int:
    argv = sys.argv[1:]
    dry_run = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    if len(args) != 1:
        print(__doc__)
        return 2
    root = Path(args[0]).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1
    count = recover(root, dry_run=dry_run)
    print(f"Done. {'Would recover' if dry_run else 'Recovered'} {count} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
