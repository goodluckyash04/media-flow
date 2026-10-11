"""Tests for file system utilities."""

from pathlib import Path
import pytest

from downloader.utils.file_utils import (
    get_directory_size,
    human_readable_size,
    is_path_within,
    safe_output_path,
    sanitize_filename,
)


def test_sanitize_filename_basic():
    assert sanitize_filename("Normal Song.mp3") == "Normal Song.mp3"
    assert sanitize_filename("Artist / Title : Song?.flac") == "Artist _ Title _ Song_.flac"
    assert sanitize_filename("Multiple   spaces    here.mp3") == "Multiple spaces here.mp3"
    assert sanitize_filename(".hidden_file.mp3") == "hidden_file.mp3"


def test_sanitize_filename_unicode():
    assert sanitize_filename("Café del Mar - Track 01.mp3") == "Café del Mar - Track 01.mp3"
    assert sanitize_filename("日本語のタイトル.mp3") == "日本語のタイトル.mp3"


def test_sanitize_filename_max_length():
    long_name = "a" * 300 + ".mp3"
    sanitized = sanitize_filename(long_name, max_length=50)
    assert len(sanitized) <= 50
    assert sanitized.endswith(".mp3")


def test_is_path_within(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    child = base / "child" / "file.mp3"
    outside = tmp_path / "other" / "file.mp3"

    assert is_path_within(child, base) is True
    assert is_path_within(base, base) is True
    assert is_path_within(outside, base) is False


def test_safe_output_path(tmp_path):
    out_dir = tmp_path / "music"
    p1 = safe_output_path(out_dir, "song.mp3")
    assert p1 == out_dir / "song.mp3"

    # Create the file so next call increments
    p1.touch()
    p2 = safe_output_path(out_dir, "song.mp3")
    assert p2 == out_dir / "song (1).mp3"

    p2.touch()
    p3 = safe_output_path(out_dir, "song.mp3")
    assert p3 == out_dir / "song (2).mp3"


def test_safe_output_path_traversal(tmp_path):
    out_dir = tmp_path / "music"
    # Even if ../ is attempted, sanitize_filename strips slashes
    p = safe_output_path(out_dir, "../../evil.mp3")
    assert is_path_within(p, out_dir)


def test_human_readable_size():
    assert human_readable_size(None) == ""
    assert human_readable_size(500) == "500.0 B"
    assert human_readable_size(1024) == "1.0 KB"
    assert human_readable_size(1024 * 1024 * 5) == "5.0 MB"
    assert human_readable_size(1024 * 1024 * 1024 * 2) == "2.0 GB"


def test_get_directory_size(tmp_path):
    f1 = tmp_path / "f1.txt"
    f1.write_bytes(b"x" * 100)
    sub = tmp_path / "sub"
    sub.mkdir()
    f2 = sub / "f2.txt"
    f2.write_bytes(b"y" * 200)

    assert get_directory_size(tmp_path) == 300
