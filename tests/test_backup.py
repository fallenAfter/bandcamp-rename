"""Tests for per-run filename journals and restore."""

from __future__ import annotations

import gzip
from pathlib import Path

from click.testing import CliRunner

import bandcamp_rename.executor as executor_mod
from bandcamp_rename.backup import RunBackup, load_journal_entries, restore_journal
from bandcamp_rename.cli import main
from bandcamp_rename.executor import apply_plan
from bandcamp_rename.models import TrackInfo
from bandcamp_rename.planner import build_plan


def _track(path: Path, **kwargs) -> TrackInfo:
    defaults = {
        "artist": "Artist",
        "album_artist": "Artist",
        "album": "Album",
        "title": "Song",
        "track_number": 1,
    }
    defaults.update(kwargs)
    return TrackInfo(path=path, **defaults)


def _album_tracks(root: Path) -> list[TrackInfo]:
    source_dir = root / "incoming" / "Artist - Album"
    source_dir.mkdir(parents=True)
    tracks: list[TrackInfo] = []
    for number, title in ((1, "One"), (2, "Two")):
        path = source_dir / f"{title.lower()}.flac"
        path.write_bytes(title.encode())
        tracks.append(
            _track(path, title=title, track_number=number, album="Album")
        )
    return tracks


def test_generate_uid_is_random_varchar(tmp_path: Path) -> None:
    first = RunBackup(directory=tmp_path / "a").uid
    second = RunBackup(directory=tmp_path / "b").uid
    assert first != second
    assert isinstance(first, str)
    assert first.isascii()
    assert "/" not in first
    assert len(first) >= 8


def test_record_move_appends_before_rename(tmp_path: Path) -> None:
    journal_dir = tmp_path / "runs"
    source = tmp_path / "old.flac"
    source.write_bytes(b"x")
    destination = tmp_path / "new.flac"
    order: list[str] = []

    backup = RunBackup(directory=journal_dir)
    original_record = RunBackup.record_move

    def tracking_record(self, *, original, source, destination):
        order.append("record")
        assert source.exists()
        return original_record(self, original=original, source=source, destination=destination)

    real_rename = Path.rename

    def tracking_rename(self, target):
        order.append("rename")
        return real_rename(self, target)

    import bandcamp_rename.backup as backup_mod

    Path.rename = tracking_rename  # type: ignore[method-assign]
    try:
        backup_mod.RunBackup.record_move = tracking_record  # type: ignore[method-assign]
        with backup:
            backup.record_move(original=source, source=source, destination=destination)
            source.rename(destination)
    finally:
        Path.rename = real_rename  # type: ignore[method-assign]
        backup_mod.RunBackup.record_move = original_record  # type: ignore[method-assign]

    assert order[:2] == ["record", "rename"]
    entries = [e for e in load_journal_entries(backup.path) if e.get("type") == "move"]
    assert entries[0]["original"] == str(source)
    assert entries[0]["to"] == str(destination)


def test_successful_run_compresses_journal(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    tracks = _album_tracks(root)
    plan = build_plan(tracks, root, update_tags=False)
    backup_dir = tmp_path / "runs"

    result = apply_plan(plan, backup_dir=backup_dir, run_uid="testrunuid1234")
    assert result.success
    assert result.run_uid == "testrunuid1234"
    assert result.journal_path is not None
    assert result.journal_path.name.endswith(".jsonl.gz")
    assert result.journal_path.is_file()
    assert not (backup_dir / "testrunuid1234.jsonl").exists()
    with gzip.open(result.journal_path, "rt", encoding="utf-8") as handle:
        contents = handle.read()
    assert str(tracks[0].path) in contents


def test_failed_run_restores_original_names(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "Music"
    tracks = _album_tracks(root)
    original_paths = [track.path for track in tracks]
    original_bytes = [path.read_bytes() for path in original_paths]
    plan = build_plan(tracks, root, update_tags=False)
    backup_dir = tmp_path / "runs"

    real_move = executor_mod._move_file
    calls = {"n": 0}

    def fail_second_move(source, destination, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("simulated failure")
        return real_move(source, destination, **kwargs)

    monkeypatch.setattr(executor_mod, "_move_file", fail_second_move)
    result = apply_plan(plan, backup_dir=backup_dir)

    assert not result.success
    assert result.restored
    assert result.journal_path is not None
    assert result.journal_path.suffix == ".jsonl"
    assert result.journal_path.is_file()
    for path, payload in zip(original_paths, original_bytes):
        assert path.is_file()
        assert path.read_bytes() == payload
    assert not (root / "Artist" / "Album" / "01 - One.flac").exists()


def test_dry_run_does_not_create_journal(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    tracks = _album_tracks(root)
    plan = build_plan(tracks, root, update_tags=False)
    backup_dir = tmp_path / "runs"
    result = apply_plan(plan, dry_run=True, backup_dir=backup_dir)
    assert result.success
    assert result.run_uid is None
    assert result.journal_path is None
    assert not backup_dir.exists() or not any(backup_dir.iterdir())


def test_recover_command_restores_from_uid(tmp_path: Path) -> None:
    journal_dir = tmp_path / "runs"
    original = tmp_path / "incoming" / "track.flac"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"audio")
    current = tmp_path / "renamed.flac"

    with RunBackup(directory=journal_dir, uid="recovermeuid123") as backup:
        backup.record_move(original=original, source=original, destination=current)
        original.rename(current)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["recover", "recovermeuid123", "--backup-dir", str(journal_dir)],
    )
    assert result.exit_code == 0, result.output
    assert original.is_file()
    assert original.read_bytes() == b"audio"
    assert not current.exists()


def test_restore_journal_dry_run_does_not_move(tmp_path: Path) -> None:
    original = tmp_path / "old.flac"
    original.write_bytes(b"x")
    current = tmp_path / "new.flac"
    journal_dir = tmp_path / "runs"
    with RunBackup(directory=journal_dir, uid="dryrestoreuid") as backup:
        backup.record_move(original=original, source=original, destination=current)
        original.rename(current)

    result = restore_journal(backup.path, dry_run=True)
    assert result.success
    assert current.is_file()
    assert not original.exists()
