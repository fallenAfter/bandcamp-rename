"""Tests for sequential per-album rename safety."""

from __future__ import annotations

from pathlib import Path

import bandcamp_rename.executor as executor_mod
from bandcamp_rename.executor import apply_plan, group_actions_by_album
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


def _write_album(
    root: Path,
    *,
    artist: str,
    album: str,
    titles: tuple[str, ...],
) -> list[TrackInfo]:
    source_dir = root / "incoming" / f"{artist} - {album}"
    source_dir.mkdir(parents=True)
    tracks: list[TrackInfo] = []
    for number, title in enumerate(titles, start=1):
        path = source_dir / f"{title}.flac"
        path.write_bytes(title.encode())
        tracks.append(
            _track(
                path,
                artist=artist,
                album_artist=artist,
                album=album,
                title=title,
                track_number=number,
            )
        )
    return tracks


def test_group_actions_by_destination_album(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    tracks = [
        *_write_album(root, artist="A", album="One", titles=("Alpha",)),
        *_write_album(root, artist="B", album="Two", titles=("Beta", "Gamma")),
    ]
    plan = build_plan(tracks, root, update_tags=False)
    batches = group_actions_by_album(plan)
    assert len(batches) == 2
    dest_parents = {batch.key for batch in batches}
    assert str(root / "A" / "One") in dest_parents
    assert str(root / "B" / "Two") in dest_parents
    sizes = sorted(len(batch.file_actions) for batch in batches)
    assert sizes == [1, 2]


def test_album_failure_stops_and_leaves_later_albums(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "Music"
    first = _write_album(root, artist="A", album="Dawn", titles=("Sun",))
    second = _write_album(root, artist="B", album="Dusk", titles=("Moon",))
    third = _write_album(root, artist="C", album="Night", titles=("Star",))
    plan = build_plan(first + second + third, root, update_tags=False)

    real_rename = executor_mod._case_safe_rename

    def fail_dusk_album(source, destination, **kwargs):
        original = kwargs.get("original") or source
        if "B - Dusk" in str(original) or "B - Dusk" in str(source):
            raise OSError("simulated album failure")
        return real_rename(source, destination, **kwargs)

    monkeypatch.setattr(executor_mod, "_case_safe_rename", fail_dusk_album)
    result = apply_plan(plan, backup_dir=tmp_path / "runs")

    assert not result.success
    assert result.failed_album is not None
    assert "Dusk" in result.failed_album or "Dusk" in (result.error or "")
    assert "stopped before remaining albums" in (result.error or "")
    assert result.restored

    assert (root / "A" / "Dawn" / "01 - Sun.flac").is_file()
    assert second[0].path.is_file()
    assert second[0].path.read_bytes() == b"Moon"
    assert not (root / "B" / "Dusk" / "01 - Moon.flac").exists()
    assert third[0].path.is_file()
    assert not (root / "C" / "Night" / "01 - Star.flac").exists()


def test_successful_multi_album_run_checkpoints_each_album(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    tracks = [
        *_write_album(root, artist="A", album="One", titles=("Alpha",)),
        *_write_album(root, artist="B", album="Two", titles=("Beta",)),
    ]
    plan = build_plan(tracks, root, update_tags=False)
    result = apply_plan(plan, backup_dir=tmp_path / "runs", run_uid="albumcheckuid")
    assert result.success
    assert (root / "A" / "One" / "01 - Alpha.flac").is_file()
    assert (root / "B" / "Two" / "01 - Beta.flac").is_file()

    from gzip import GzipFile

    assert result.journal_path is not None
    with GzipFile(result.journal_path, "r") as handle:
        text = handle.read().decode("utf-8")
    assert text.count('"type": "checkpoint"') == 2
