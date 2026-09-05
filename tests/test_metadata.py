"""Tests for metadata reading and fallback parsing."""

from bandcamp_rename.metadata import read_track_info, read_tracks
from bandcamp_rename.models import MetadataSource


def test_read_track_info_from_tags(make_audio) -> None:
    path = make_audio(
        "Artist/Album/01 - Song.mp3",
        artist="Track Artist",
        albumartist="Album Artist",
        album="Album Title",
        title="Song",
        tracknumber="1",
        discnumber="2",
    )

    info = read_track_info(path)

    assert info.artist == "Track Artist"
    assert info.album_artist == "Album Artist"
    assert info.album == "Album Title"
    assert info.title == "Song"
    assert info.track_number == 1
    assert info.disc_number == 2
    assert MetadataSource.TAGS in info.sources
    assert info.has_minimum_metadata()


def test_read_track_info_bandcamp_filename_fallback(make_flac) -> None:
    path = make_flac("incoming/Artist - Album/Artist - Album - 03 Third Track.flac")

    info = read_track_info(path)

    assert info.artist == "Artist"
    assert info.album == "Album"
    assert info.title == "Third Track"
    assert info.track_number == 3
    assert MetadataSource.BANDCAMP_FILENAME in info.sources
    assert info.has_minimum_metadata()


def test_read_track_info_generic_filename_and_folder_fallback(tmp_path) -> None:
    album_dir = tmp_path / "Artist Name" / "Album Title"
    album_dir.mkdir(parents=True)
    path = album_dir / "02 - Second Song.flac"
    path.write_bytes(b"not-a-real-flac")

    info = read_track_info(path)

    assert info.artist == "Artist Name"
    assert info.album == "Album Title"
    assert info.title == "Second Song"
    assert info.track_number == 2
    assert MetadataSource.GENERIC_FILENAME in info.sources
    assert MetadataSource.PARENT_FOLDER in info.sources
    assert info.has_minimum_metadata()


def test_read_track_info_flags_compilation(make_audio) -> None:
    path = make_audio(
        "Various Artists/Sampler/01 - Song.mp3",
        artist="Some Artist",
        albumartist="Various Artists",
        album="Sampler",
        title="Song",
    )

    info = read_track_info(path)

    assert info.is_compilation
    assert info.album_artist == "Various Artists"


def test_read_track_info_missing_metadata(make_flac) -> None:
    path = make_flac("incoming/track.flac")

    info = read_track_info(path)

    assert not info.has_minimum_metadata()
    assert info.missing_fields() == ["album_artist", "title"]


def test_read_tracks(make_audio) -> None:
    first = make_audio("a/01 - One.mp3", title="One", artist="A", album="B")
    second = make_audio("a/02 - Two.mp3", title="Two", artist="A", album="B")

    tracks = read_tracks([first, second])

    assert len(tracks) == 2
    assert tracks[0].title == "One"
    assert tracks[1].title == "Two"
