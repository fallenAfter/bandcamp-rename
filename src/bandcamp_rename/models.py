"""Core data models for track metadata and scan results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class MetadataSource(str, Enum):
    """Where track metadata was resolved from."""

    TAGS = "tags"
    BANDCAMP_FILENAME = "bandcamp_filename"
    GENERIC_FILENAME = "generic_filename"
    BANDCAMP_FOLDER = "bandcamp_folder"
    PARENT_FOLDER = "parent_folder"


@dataclass
class TrackInfo:
    """Structured metadata for a single audio track."""

    path: Path
    artist: str | None = None
    album_artist: str | None = None
    album: str | None = None
    title: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    is_compilation: bool = False
    sources: set[MetadataSource] = field(default_factory=set)

    @property
    def effective_album_artist(self) -> str | None:
        """Album artist tag, falling back to track artist."""
        return self.album_artist or self.artist

    def has_minimum_metadata(self) -> bool:
        """Return True when enough metadata exists to organize this track.

        Album is optional — missing albums are filed under Singles.
        """
        return bool(self.effective_album_artist and self.title)

    def missing_fields(self) -> list[str]:
        """Return names of required fields that are still missing."""
        missing: list[str] = []
        if not self.effective_album_artist:
            missing.append("album_artist")
        if not self.title:
            missing.append("title")
        return missing


@dataclass
class ScanResult:
    """Files discovered while scanning a directory tree."""

    root: Path
    audio_files: list[Path] = field(default_factory=list)
    zip_files: list[Path] = field(default_factory=list)
    companion_files: list[Path] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.audio_files) + len(self.zip_files) + len(self.companion_files)
