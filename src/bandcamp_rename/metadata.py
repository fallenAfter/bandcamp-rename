"""Read and enrich track metadata from tags, filenames, and folders."""

from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, ID3NoHeaderError

from bandcamp_rename.bandcamp import (
    parse_bandcamp_filename,
    parse_bandcamp_folder,
    parse_generic_filename,
)
from bandcamp_rename.models import MetadataSource, TrackInfo

COMPILATION_ALBUM_ARTISTS = frozenset({"various artists"})
STAGING_FOLDER_NAMES = frozenset({"music", "incoming", "downloads"})


def _first_text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    text = str(value).strip()
    return text or None


def _parse_int(value: object | None) -> int | None:
    text = _first_text(value)
    if not text:
        return None
    # Tags often use "1/12" — take the first component only.
    primary = text.split("/", 1)[0].strip()
    digits = "".join(ch for ch in primary if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def _read_id3_tags(path: Path, info: TrackInfo) -> bool:
    """Read ID3 tags directly (works on tag-only MP3 test files)."""
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        return False
    except Exception:
        return False

    info.artist = _first_text(id3.get("TPE1"))
    info.album_artist = _first_text(id3.get("TPE2"))
    info.album = _first_text(id3.get("TALB"))
    info.title = _first_text(id3.get("TIT2"))
    info.track_number = _parse_int(id3.get("TRCK"))
    info.disc_number = _parse_int(id3.get("TPOS"))
    return any([info.artist, info.album_artist, info.album, info.title])


def _read_tags(path: Path) -> TrackInfo:
    info = TrackInfo(path=path)

    audio = None
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None

    if audio is None:
        if path.suffix.lower() == ".mp3" and _read_id3_tags(path, info):
            info.sources.add(MetadataSource.TAGS)
        return info

    info.artist = _first_text(audio.get("artist"))
    info.album_artist = _first_text(audio.get("albumartist"))
    info.album = _first_text(audio.get("album"))
    info.title = _first_text(audio.get("title"))
    info.track_number = _parse_int(audio.get("tracknumber"))
    info.disc_number = _parse_int(audio.get("discnumber"))

    if info.album_artist and info.album_artist.lower() in COMPILATION_ALBUM_ARTISTS:
        info.is_compilation = True

    if any([info.artist, info.album_artist, info.album, info.title]):
        info.sources.add(MetadataSource.TAGS)

    return info


def _apply_parsed(info: TrackInfo, parsed, source: MetadataSource) -> None:
    if parsed.artist and not info.artist:
        info.artist = parsed.artist
    if parsed.album and not info.album:
        info.album = parsed.album
    if parsed.title and not info.title:
        info.title = parsed.title
    if parsed.track_number is not None and info.track_number is None:
        info.track_number = parsed.track_number
    info.sources.add(source)


def _apply_folder_context(info: TrackInfo, path: Path) -> None:
    parent = path.parent.name
    grandparent = path.parent.parent.name if path.parent.parent != path.parent else None

    if " - " in parent:
        bandcamp_parent = parse_bandcamp_folder(parent)
        if bandcamp_parent.artist and not info.artist:
            info.artist = bandcamp_parent.artist
        if bandcamp_parent.album and not info.album:
            info.album = bandcamp_parent.album
        info.sources.add(MetadataSource.BANDCAMP_FOLDER)
        return

    if grandparent and grandparent.lower() not in STAGING_FOLDER_NAMES:
        if parent.lower() in STAGING_FOLDER_NAMES:
            return
        if not info.artist:
            info.artist = grandparent
            info.sources.add(MetadataSource.PARENT_FOLDER)
        if not info.album:
            info.album = parent
            info.sources.add(MetadataSource.PARENT_FOLDER)


def read_track_info(path: Path) -> TrackInfo:
    """Read track metadata using tags first, then filename and folder fallbacks."""
    info = _read_tags(path)

    bandcamp_parsed = parse_bandcamp_filename(path.name)
    if bandcamp_parsed:
        _apply_parsed(info, bandcamp_parsed, MetadataSource.BANDCAMP_FILENAME)
    else:
        generic_parsed = parse_generic_filename(path.name)
        if generic_parsed:
            _apply_parsed(info, generic_parsed, MetadataSource.GENERIC_FILENAME)

    if not info.has_minimum_metadata():
        _apply_folder_context(info, path)

    if info.album_artist and info.album_artist.lower() in COMPILATION_ALBUM_ARTISTS:
        info.is_compilation = True

    return info


def read_tracks(paths: list[Path]) -> list[TrackInfo]:
    """Read metadata for multiple audio file paths."""
    return [read_track_info(path) for path in paths]
