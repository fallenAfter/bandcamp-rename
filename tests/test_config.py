"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

from bandcamp_rename.config import AppConfig, load_config, merge_cli_overrides


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.yaml")
    assert isinstance(config, AppConfig)
    assert ".flac" in config.audio_extensions
    assert config.auto_unpack_zips is False


def test_load_config_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "\n".join(
            [
                "root: /mnt/plex/Music",
                "audio_extensions: [.flac, mp3]",
                "track_filename_template: '{track:02d}. {title}'",
                "auto_unpack_zips: true",
                "skip_files: [cover.jpg]",
            ]
        )
    )
    config = load_config(path)
    assert config.root == Path("/mnt/plex/Music")
    assert config.audio_extensions == frozenset({".flac", ".mp3"})
    assert config.track_filename_template == "{track:02d}. {title}"
    assert config.auto_unpack_zips is True
    assert config.skip_files == frozenset({"cover.jpg"})


def test_merge_cli_overrides() -> None:
    config = AppConfig()
    merged = merge_cli_overrides(
        config,
        extensions=frozenset({".ogg"}),
        auto_unpack=True,
    )
    assert merged.audio_extensions == frozenset({".ogg"})
    assert merged.auto_unpack_zips is True
    assert config.audio_extensions != frozenset({".ogg"})


def test_to_plex_rules_uses_templates(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("multi_disc_filename_template: '{disc}-{track:02d} {title}'\n")
    rules = load_config(path).to_plex_rules()
    assert rules.multi_disc_filename_template == "{disc}-{track:02d} {title}"
