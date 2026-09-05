"""Tests for Singles filing and orphaned ZIP cleanup."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from bandcamp_rename.bandcamp import cleanup_orphaned_zips, is_orphaned_bandcamp_zip
from bandcamp_rename.cli import main
from bandcamp_rename.executor import apply_plan
from bandcamp_rename.models import TrackInfo
from bandcamp_rename.planner import build_plan
from bandcamp_rename.plex_rules import expected_path, target_album_folder


def test_missing_album_uses_singles_folder() -> None:
    track = TrackInfo(
        path=Path("/tmp/song.flac"),
        artist="Venjent",
        title="All The Things She Said (Bootleg)",
    )
    assert target_album_folder(track) == "Singles"
    assert expected_path(Path("/Music"), track) == Path(
        "/Music/Venjent/Singles/01 - All The Things She Said (Bootleg).flac"
    )


def test_root_level_single_is_planned(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    source = root / "Venjent - All The Things She Said (Bootleg).flac"
    source.write_bytes(b"x")
    track = TrackInfo(
        path=source,
        artist="Venjent",
        title="All The Things She Said (Bootleg)",
    )
    plan = build_plan([track], root, update_tags=False)
    assert track.path not in plan.skipped
    assert len([a for a in plan.actions if a.destination]) >= 1
    result = apply_plan(plan)
    assert result.success
    assert (
        root / "Venjent" / "Singles" / "01 - All The Things She Said (Bootleg).flac"
    ).is_file()
    assert not source.exists()


def test_orphaned_zip_detected_when_extract_folder_gone(tmp_path: Path, make_zip) -> None:
    zip_path = make_zip("Artist - Album.zip", {"track.flac": b"x"})
    # No extract folder → treated as orphaned leftover after a fix.
    assert is_orphaned_bandcamp_zip(zip_path) is True

    extract_dir = zip_path.parent / zip_path.stem
    extract_dir.mkdir()
    (extract_dir / "track.flac").write_bytes(b"audio")
    assert is_orphaned_bandcamp_zip(zip_path) is False

    (extract_dir / "track.flac").unlink()
    assert is_orphaned_bandcamp_zip(zip_path) is True


def test_fix_removes_orphaned_zip(tmp_path: Path, make_zip) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    zip_path = make_zip(
        "Music/Artist - Album.zip",
        {"track.flac": b"x"},
    )
    # No extract folder remains — ZIP is orphaned.
    assert not (root / "Artist - Album").exists()

    runner = CliRunner()
    result = runner.invoke(main, ["fix", str(root), "--dry-run"])
    assert result.exit_code == 0
    assert "Would remove orphaned zip" in result.output
    assert zip_path.exists()

    result = runner.invoke(main, ["fix", str(root)])
    assert result.exit_code == 0
    assert "Removed orphaned zip" in result.output
    assert not zip_path.exists()


def test_cleanup_orphaned_zips_helper(tmp_path: Path, make_zip) -> None:
    zip_path = make_zip("Artist - Album.zip", {"a.flac": b"x"})
    extract = zip_path.parent / "Artist - Album"
    extract.mkdir()
    removed = cleanup_orphaned_zips(zip_path.parent, dry_run=False)
    assert zip_path in removed
    assert not zip_path.exists()
