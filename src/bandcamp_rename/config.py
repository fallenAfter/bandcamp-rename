"""Load and merge user configuration."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from bandcamp_rename.plex_rules import PlexRulesConfig
from bandcamp_rename.scanner import DEFAULT_AUDIO_EXTENSIONS, DEFAULT_SKIP_FILENAMES


@dataclass
class AppConfig:
    """Runtime configuration for bandcamp-rename."""

    root: Path | None = None
    audio_extensions: frozenset[str] = field(
        default_factory=lambda: DEFAULT_AUDIO_EXTENSIONS
    )
    compilation_album_artist: str = "Various Artists"
    singles_album_name: str = "Singles"
    track_filename_template: str = "{track:02d} - {title}"
    multi_disc_filename_template: str = "{disc}{track:02d} - {title}"
    skip_files: frozenset[str] = field(default_factory=lambda: DEFAULT_SKIP_FILENAMES)
    update_tags_after_move: bool = True
    treat_missing_albumartist_as_artist: bool = True
    auto_unpack_zips: bool = False
    delete_zip_after_unpack: bool = False
    delete_orphaned_zips_after_fix: bool = True
    move_cover_art: bool = True

    def to_plex_rules(self) -> PlexRulesConfig:
        return PlexRulesConfig(
            compilation_album_artist=self.compilation_album_artist,
            singles_album_name=self.singles_album_name,
            track_filename_template=self.track_filename_template,
            multi_disc_filename_template=self.multi_disc_filename_template,
            treat_missing_albumartist_as_artist=self.treat_missing_albumartist_as_artist,
        )


def default_config_path() -> Path:
    """Return the XDG-style default config path."""
    return Path.home() / ".config" / "bandcamp-rename" / "config.yaml"


def _normalize_extensions(values: list[str] | None) -> frozenset[str]:
    if values is None:
        return DEFAULT_AUDIO_EXTENSIONS
    normalized = []
    for value in values:
        text = str(value).strip().lower()
        if not text:
            continue
        normalized.append(text if text.startswith(".") else f".{text}")
    return frozenset(normalized) if normalized else DEFAULT_AUDIO_EXTENSIONS


def _normalize_skip_files(values: list[str] | None) -> frozenset[str]:
    if values is None:
        return DEFAULT_SKIP_FILENAMES
    return frozenset(str(v).lower() for v in values)


def _coerce_bool(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
    raise ValueError(f"Config field '{field_name}' must be a boolean, got {value!r}")


_BOOL_FIELDS = frozenset(
    {
        "update_tags_after_move",
        "treat_missing_albumartist_as_artist",
        "auto_unpack_zips",
        "delete_zip_after_unpack",
        "delete_orphaned_zips_after_fix",
        "move_cover_art",
    }
)


def load_config(path: Path | None = None) -> AppConfig:
    """Load config from *path*, or the default location if present."""
    config_path = path or default_config_path()
    if not config_path.is_file():
        return AppConfig()

    raw = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a mapping: {config_path}")

    data: dict = {}
    known = {f.name for f in fields(AppConfig)}
    for key, value in raw.items():
        if key not in known:
            continue
        data[key] = value

    if "root" in data and data["root"] is not None:
        data["root"] = Path(str(data["root"])).expanduser()
    if "audio_extensions" in data:
        data["audio_extensions"] = _normalize_extensions(data["audio_extensions"])
    if "skip_files" in data:
        data["skip_files"] = _normalize_skip_files(data["skip_files"])
    for bool_field in _BOOL_FIELDS:
        if bool_field in data:
            data[bool_field] = _coerce_bool(data[bool_field], field_name=bool_field)

    return AppConfig(**data)


def merge_cli_overrides(
    config: AppConfig,
    *,
    extensions: frozenset[str] | None = None,
    auto_unpack: bool | None = None,
) -> AppConfig:
    """Return a copy of *config* with CLI overrides applied."""
    updated = AppConfig(**{f.name: getattr(config, f.name) for f in fields(config)})
    if extensions is not None:
        updated.audio_extensions = extensions
    if auto_unpack is not None:
        updated.auto_unpack_zips = auto_unpack
    return updated
