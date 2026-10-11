"""Tests for services: conversion, metadata, download, and spotify."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from downloader.models import AppSettings, AudioFormat, ConversionJob, DownloadJob, JobStatus
from downloader.services.conversion_service import (
    _build_ffmpeg_cmd,
    detect_ffmpeg,
    detect_ffprobe,
    probe_file,
)
from downloader.services.download_service import _ProgressHook
from downloader.services.metadata_service import fetch_media_info, fetch_playlist_info
from downloader.services.spotify_service import SpotifyServiceUnavailable, is_spotify_url


def test_detect_ffmpeg_mocked():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ffmpeg version 6.0 Copyright (c) 2000-2023\n")
        available, version = detect_ffmpeg("ffmpeg")
        assert available is True
        assert "ffmpeg version 6.0" in version

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError()
        available, version = detect_ffmpeg("nonexistent_ffmpeg")
        assert available is False
        assert version == ""


def test_detect_ffprobe_mocked():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ffprobe version 6.0\n")
        available, version = detect_ffprobe("ffprobe")
        assert available is True
        assert "ffprobe version 6.0" in version


@pytest.mark.django_db
def test_build_ffmpeg_cmd():
    job = ConversionJob(
        output_format="mp3",
        output_quality="high",
    )
    cmd = _build_ffmpeg_cmd(
        ffmpeg="ffmpeg",
        input_path=Path("input.mp4"),
        output_path=Path("output.mp3"),
        job=job,
    )
    cmd_str = " ".join(cmd)
    assert "-codec:a libmp3lame" in cmd_str
    assert "-vn" in cmd_str
    assert "-y" in cmd_str
    assert "output.mp3" in cmd_str

    # Test flac format
    job.output_format = "flac"
    cmd_flac = _build_ffmpeg_cmd(
        ffmpeg="ffmpeg",
        input_path=Path("input.mp4"),
        output_path=Path("output.flac"),
        job=job,
    )
    assert "-codec:a flac" in " ".join(cmd_flac)


@pytest.mark.django_db
def test_probe_file_mocked():
    fake_json = (
        '{"format": {"duration": "120.5", "size": "1048576", "format_name": "mp3"}, '
        '"streams": [{"codec_type": "audio", "codec_name": "mp3", "bit_rate": "320000"}]}'
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_json)
        info = probe_file(Path("fake.mp3"))
        assert info["duration"] == 120.5
        assert info["size"] == 1048576
        assert info["audio_codec"] == "mp3"
        assert info["has_audio"] is True
        assert info["has_video"] is False


def test_is_spotify_url():
    assert is_spotify_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") is True
    assert is_spotify_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") is True
    assert is_spotify_url("spotify:track:4cOdK2wGLETKBW3PvgPWqT") is True
    assert is_spotify_url("https://www.youtube.com/watch?v=123") is False


def test_fetch_media_info_mocked():
    sample_info = {
        "title": "Test Title",
        "uploader": "Test Artist",
        "duration": 200,
        "thumbnail": "https://example.com/thumb.jpg",
        "description": "A description",
        "webpage_url": "https://example.com/video",
        "extractor": "youtube",
        "is_live": False,
        "upload_date": "20260101",
    }
    with patch("yt_dlp.YoutubeDL") as mock_ydl_class:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = sample_info
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        info = fetch_media_info("https://example.com/video")
        assert info["title"] == "Test Title"
        assert info["uploader"] == "Test Artist"
        assert info["duration"] == 200


def test_fetch_playlist_info_mocked():
    sample_playlist = {
        "title": "My Playlist",
        "uploader": "Curator",
        "webpage_url": "https://example.com/playlist",
        "entries": [
            {
                "url": "https://example.com/track1",
                "title": "Track 1",
                "uploader": "Artist 1",
                "duration": 180,
                "id": "trk1",
            },
            {
                "url": "https://example.com/track2",
                "title": "Track 2",
                "uploader": "Artist 2",
                "duration": 210,
                "id": "trk2",
            },
        ],
    }
    with patch("yt_dlp.YoutubeDL") as mock_ydl_class:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = sample_playlist
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        info = fetch_playlist_info("https://example.com/playlist")
        assert info["title"] == "My Playlist"
        assert info["entry_count"] == 2
        assert len(info["entries"]) == 2
        assert info["entries"][0]["title"] == "Track 1"


@pytest.mark.django_db
def test_progress_hook():
    job = DownloadJob.objects.create(url="https://example.com/video")
    cancel_flag = False

    hook = _ProgressHook(str(job.id), lambda: cancel_flag)

    # Simulate downloading progress
    hook({
        "status": "downloading",
        "total_bytes": 1000000,
        "downloaded_bytes": 500000,
        "_speed_str": "1.5 MiB/s",
        "_eta_str": "00:05",
    })

    job.refresh_from_db()
    assert job.progress_pct == 50.0
    assert job.speed == "1.5 MiB/s"
    assert job.eta == "00:05"
    assert job.stage == "Downloading"
