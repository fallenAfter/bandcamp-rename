"""Reusable fixture builders for integration-style tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1, TPE2, TRCK


def write_tagged_mp3(
    path: Path,
    *,
    artist: str | None = None,
    albumartist: str | None = None,
    album: str | None = None,
    title: str | None = None,
    tracknumber: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ID3")
    tags = ID3()
    if title:
        tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))
    if albumartist:
        tags.add(TPE2(encoding=3, text=albumartist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    if tracknumber:
        tags.add(TRCK(encoding=3, text=tracknumber))
    tags.save(path)
    return path


def build_bandcamp_zip(destination: Path) -> Path:
    """Create a Bandcamp-style ZIP under *destination* parent."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as archive:
        archive.writestr(
            "Artist - Album/Artist - Album - 01 First Track.flac",
            b"track1",
        )
        archive.writestr(
            "Artist - Album/Artist - Album - 02 Second Track.flac",
            b"track2",
        )
        archive.writestr("Artist - Album/cover.jpg", b"cover")
    return destination


def build_compliant_album(root: Path) -> Path:
    album = root / "Artist" / "Album"
    write_tagged_mp3(
        album / "01 - Song.mp3",
        artist="Artist",
        albumartist="Artist",
        album="Album",
        title="Song",
        tracknumber="1",
    )
    return album
