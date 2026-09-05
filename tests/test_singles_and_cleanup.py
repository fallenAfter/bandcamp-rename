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


def test_never_extracted_zip_is_not_orphaned(tmp_path: Path, make_zip) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    zip_path = make_zip("Music/Artist - Album.zip", {"track.flac": b"x"})
    # ZIP only — no organized album yet — must not delete.
    assert is_orphaned_bandcamp_zip(zip_path, root) is False


def test_orphaned_zip_requires_organized_album(tmp_path: Path, make_zip) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    zip_path = make_zip(
        "Music/Artist - Album [flac].zip",
        {"track.flac": b"x"},
    )
    assert is_orphaned_bandcamp_zip(zip_path, root) is False

    organized = root / "Artist" / "Album"
    organized.mkdir(parents=True)
    (organized / "01 - Song.flac").write_bytes(b"audio")
    assert is_orphaned_bandcamp_zip(zip_path, root) is True


def test_zip_with_extracted_audio_is_not_orphaned(tmp_path: Path, make_zip) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    zip_path = make_zip("Music/Artist - Album.zip", {"track.flac": b"x"})
    extract_dir = root / "Artist - Album"
    extract_dir.mkdir()
    (extract_dir / "track.flac").write_bytes(b"audio")
    organized = root / "Artist" / "Album"
    organized.mkdir(parents=True)
    (organized / "01 - Song.flac").write_bytes(b"audio")
    assert is_orphaned_bandcamp_zip(zip_path, root) is False


def test_fix_removes_orphaned_zip(tmp_path: Path, make_zip) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    zip_path = make_zip(
        "Music/Artist - Album.zip",
        {"track.flac": b"x"},
    )
    organized = root / "Artist" / "Album"
    organized.mkdir(parents=True)
    (organized / "01 - Song.flac").write_bytes(b"audio")

    runner = CliRunner()
    result = runner.invoke(main, ["fix", str(root), "--dry-run"])
    assert result.exit_code == 0
    assert "Would remove orphaned zip" in result.output
    assert zip_path.exists()

    result = runner.invoke(main, ["fix", str(root)])
    assert result.exit_code == 0
    assert "Removed orphaned zip" in result.output
    assert not zip_path.exists()


def test_fix_keeps_never_extracted_zip(tmp_path: Path, make_zip) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    zip_path = make_zip(
        "Music/Artist - Album.zip",
        {"track.flac": b"x"},
    )
    runner = CliRunner()
    result = runner.invoke(main, ["fix", str(root)])
    assert result.exit_code == 0
    assert "Removed orphaned zip" not in result.output
    assert zip_path.exists()


def test_cleanup_orphaned_zips_helper(tmp_path: Path, make_zip) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    zip_path = make_zip("Music/Artist - Album.zip", {"a.flac": b"x"})
    organized = root / "Artist" / "Album"
    organized.mkdir(parents=True)
    (organized / "01 - Song.flac").write_bytes(b"x")
    removed = cleanup_orphaned_zips(root, dry_run=False)
    assert zip_path in removed
    assert not zip_path.exists()
