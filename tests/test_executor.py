"""Integration-style tests for the executor."""

from __future__ import annotations

from pathlib import Path

from bandcamp_rename.executor import apply_plan
from bandcamp_rename.models import TrackInfo
from bandcamp_rename.planner import build_plan


def test_messy_tree_to_plex_layout(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    album_dir = root / "Bandcamp Dump" / "The Band - Night Songs"
    album_dir.mkdir(parents=True)
    files = [
        ("The Band - Night Songs - 01 Intro.flac", "Intro", 1),
        ("The Band - Night Songs - 02 Outro.flac", "Outro", 2),
    ]
    tracks: list[TrackInfo] = []
    for filename, title, number in files:
        path = album_dir / filename
        path.write_bytes(b"x")
        tracks.append(
            TrackInfo(
                path=path,
                artist="The Band",
                album_artist="The Band",
                album="Night Songs",
                title=title,
                track_number=number,
            )
        )

    plan = build_plan(tracks, root, update_tags=False)
    result = apply_plan(plan)

    assert result.success
    assert (root / "The Band" / "Night Songs" / "01 - Intro.flac").is_file()
    assert (root / "The Band" / "Night Songs" / "02 - Outro.flac").is_file()
