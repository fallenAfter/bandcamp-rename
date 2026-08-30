"""Tests for Bandcamp filename, folder, and ZIP helpers."""

from pathlib import Path

from bandcamp_rename.bandcamp import (
    extract_zip,
    is_bandcamp_zip,
    parse_bandcamp_filename,
    parse_bandcamp_folder,
    parse_generic_filename,
)


def test_is_bandcamp_zip() -> None:
    assert is_bandcamp_zip(Path("Artist - Album.zip"))
    assert not is_bandcamp_zip(Path("random.zip"))
    assert not is_bandcamp_zip(Path("track.flac"))


def test_parse_bandcamp_folder() -> None:
    parsed = parse_bandcamp_folder("The Band - Night Album")
    assert parsed.artist == "The Band"
    assert parsed.album == "Night Album"


def test_parse_bandcamp_folder_artist_with_dash() -> None:
    parsed = parse_bandcamp_folder("A - B - Greatest Hits")
    assert parsed.artist == "A - B"
    assert parsed.album == "Greatest Hits"


def test_parse_bandcamp_filename() -> None:
    parsed = parse_bandcamp_filename("Artist - Album - 01 Track One.flac")
    assert parsed is not None
    assert parsed.artist == "Artist"
    assert parsed.album == "Album"
    assert parsed.track_number == 1
    assert parsed.title == "Track One"


def test_parse_bandcamp_filename_with_dash_before_title() -> None:
    parsed = parse_bandcamp_filename("Artist - Album - 02 - Track Two.mp3")
    assert parsed is not None
    assert parsed.track_number == 2
    assert parsed.title == "Track Two"


def test_parse_generic_filename() -> None:
    parsed = parse_generic_filename("01 - Opening.flac")
    assert parsed is not None
    assert parsed.track_number == 1
    assert parsed.title == "Opening"


def test_parse_generic_filename_dot_separator() -> None:
    parsed = parse_generic_filename("03. Deep Cut.mp3")
    assert parsed is not None
    assert parsed.track_number == 3
    assert parsed.title == "Deep Cut"


def test_extract_zip(tmp_path, make_zip) -> None:
    zip_path = make_zip(
        "Artist - Album.zip",
        {"Artist - Album/Artist - Album - 01 Track One.flac": b"fake"},
    )
    extracted = extract_zip(zip_path)
    assert extracted.is_dir()
    assert (extracted / "Artist - Album" / "Artist - Album - 01 Track One.flac").is_file()


def test_extract_zip_skips_existing_non_empty_dir(tmp_path, make_zip) -> None:
    zip_path = make_zip("Artist - Album.zip", {"track.flac": b"fake"})
    existing = tmp_path / "Artist - Album"
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_text("stay")

    extracted = extract_zip(zip_path)
    assert extracted == existing
    assert marker.read_text() == "stay"
