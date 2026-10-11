"""Tests for input validation functions."""

import pytest
from django.core.exceptions import ValidationError

from downloader.utils.validators import (
    validate_audio_format,
    validate_audio_quality,
    validate_filename_template,
    validate_output_dir,
    validate_url,
)


def test_validate_url_valid():
    assert validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert validate_url("https://soundcloud.com/artist/track") == "https://soundcloud.com/artist/track"
    assert validate_url("http://example.com/audio.mp3") == "http://example.com/audio.mp3"


def test_validate_url_invalid():
    with pytest.raises(ValidationError, match="URL is required"):
        validate_url("")

    with pytest.raises(ValidationError, match="Unsupported URL scheme"):
        validate_url("ftp://example.com/file.mp3")

    with pytest.raises(ValidationError, match="valid hostname"):
        validate_url("https://")

    with pytest.raises(ValidationError, match="localhost are not permitted"):
        validate_url("http://localhost:8000/media")

    with pytest.raises(ValidationError, match="private or local network addresses"):
        validate_url("http://127.0.0.1:8000/media")

    with pytest.raises(ValidationError, match="private or local network"):
        validate_url("http://192.168.1.1/video")


def test_validate_output_dir(tmp_path):
    valid_dir = tmp_path / "downloads"
    valid_dir.mkdir()
    resolved = validate_output_dir(str(valid_dir))
    assert resolved == valid_dir.resolve()

    with pytest.raises(ValidationError, match="Output directory is required"):
        validate_output_dir("")


def test_validate_audio_format():
    assert validate_audio_format("mp3") == "mp3"
    assert validate_audio_format("flac") == "flac"
    assert validate_audio_format("m4a") == "m4a"

    with pytest.raises(ValidationError, match="Unsupported audio format"):
        validate_audio_format("exe")


def test_validate_audio_quality():
    assert validate_audio_quality("best", "mp3") == "best"
    assert validate_audio_quality("high", "mp3") == "high"
    assert validate_audio_quality("best", "flac") == "best"

    with pytest.raises(ValidationError, match="is not available for format"):
        validate_audio_quality("999", "mp3")


def test_validate_filename_template():
    assert validate_filename_template("%(title)s - %(uploader)s") == "%(title)s - %(uploader)s"

    with pytest.raises(ValidationError, match="cannot be empty"):
        validate_filename_template("")

    with pytest.raises(ValidationError, match="must contain at least one yt-dlp variable"):
        validate_filename_template("fixed_filename_without_vars")

    with pytest.raises(ValidationError, match="forbidden characters"):
        validate_filename_template("%(title)s <bad>")
