"""Tests for filesystem name sanitization."""

from bandcamp_rename.sanitize import sanitize_filename, sanitize_name


def test_sanitize_replaces_invalid_chars() -> None:
    assert sanitize_name('A:B/C|D*E?F"G<H>I') == "A_B_C_D_E_F_G_H_I"


def test_sanitize_collapses_whitespace() -> None:
    assert sanitize_name("  Foo   Bar  ") == "Foo Bar"


def test_sanitize_strips_trailing_dots() -> None:
    assert sanitize_name("Album...") == "Album"


def test_sanitize_empty_becomes_unknown() -> None:
    assert sanitize_name("") == "Unknown"
    assert sanitize_name("   ") == "Unknown"


def test_sanitize_filename() -> None:
    assert sanitize_filename("Track: One") == "Track_ One"
