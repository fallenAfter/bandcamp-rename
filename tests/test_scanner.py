"""Tests for directory scanning."""


from bandcamp_rename.scanner import scan_directory


def test_scan_directory_finds_audio_zip_and_companion(tmp_path, make_flac, make_zip) -> None:
    album_dir = tmp_path / "Artist - Album"
    album_dir.mkdir()
    make_flac("Artist - Album/Artist - Album - 01 Track One.flac")
    (album_dir / "cover.jpg").write_bytes(b"img")
    make_zip("Artist - Album.zip", {"track.flac": b"x"})
    (tmp_path / "notes.txt").write_text("ignore me")

    result = scan_directory(tmp_path)

    assert len(result.audio_files) == 1
    assert result.audio_files[0].name.endswith("Track One.flac")
    assert len(result.zip_files) == 1
    assert result.zip_files[0].name == "Artist - Album.zip"
    assert len(result.companion_files) == 1
    assert result.companion_files[0].name == "cover.jpg"


def test_scan_directory_recursive(tmp_path, make_flac) -> None:
    make_flac("nested/Artist/Album/01 - Song.flac")

    result = scan_directory(tmp_path)

    assert len(result.audio_files) == 1
    assert result.audio_files[0].name == "01 - Song.flac"
