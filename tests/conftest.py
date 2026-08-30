"""Shared pytest fixtures for bandcamp-rename tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TPE2, TPOS, TRCK


def _write_id3_tags(
    path: Path,
    *,
    artist: str | None = None,
    albumartist: str | None = None,
    album: str | None = None,
    title: str | None = None,
    tracknumber: str | None = None,
    discnumber: str | None = None,
) -> None:
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
    if discnumber:
        tags.add(TPOS(encoding=3, text=discnumber))
    tags.save(path)


@pytest.fixture
def make_audio(tmp_path: Path):
    """Factory for creating tagged audio files (MP3 with ID3 tags)."""

    def _make_audio(
        relative_path: str,
        *,
        artist: str | None = None,
        albumartist: str | None = None,
        album: str | None = None,
        title: str | None = None,
        tracknumber: str | None = None,
        discnumber: str | None = None,
    ) -> Path:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ID3")
        _write_id3_tags(
            path,
            artist=artist,
            albumartist=albumartist,
            album=album,
            title=title,
            tracknumber=tracknumber,
            discnumber=discnumber,
        )
        return path

    return _make_audio


@pytest.fixture
def make_flac(tmp_path: Path):
    """Factory for creating placeholder audio files by extension."""

    def _make_flac(relative_path: str, **tags: str | None) -> Path:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if tags:
            path.write_bytes(b"ID3")
            _write_id3_tags(
                path,
                artist=tags.get("artist"),
                albumartist=tags.get("albumartist"),
                album=tags.get("album"),
                title=tags.get("title"),
                tracknumber=tags.get("tracknumber"),
                discnumber=tags.get("discnumber"),
            )
        else:
            path.write_bytes(b"")
        return path

    return _make_flac


@pytest.fixture
def make_zip(tmp_path: Path):
    """Factory for creating ZIP archives."""

    def _make_zip(name: str, files: dict[str, bytes]) -> Path:
        zip_path = tmp_path / name
        with zipfile.ZipFile(zip_path, "w") as archive:
            for filename, content in files.items():
                archive.writestr(filename, content)
        return zip_path

    return _make_zip
