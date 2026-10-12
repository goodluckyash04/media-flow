"""Comprehensive tests for audio quality modes, FFprobe inspection, and refined UI."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from downloader.models import AppSettings, AudioFormat, ConversionJob, DownloadJob, JobStatus
from downloader.services.conversion_service import _build_ffmpeg_cmd, probe_file
from downloader.services.download_service import _build_ydl_opts, run_download_job
from downloader.utils.validators import validate_audio_quality


@pytest.mark.django_db
def test_original_mode_ydl_opts():
    """Verify Mode A (Original / Best Available) avoids FFmpegExtractAudio."""
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=dummy123",
        audio_only=True,
        output_format="original",
        output_quality="original",
    )
    opts = _build_ydl_opts(job, Path("/tmp"), lambda: False)
    assert opts["format"] == "bestaudio/best"
    
    # Ensure FFmpegExtractAudio is NOT present in postprocessors
    pp_keys = [p.get("key") for p in opts.get("postprocessors", [])]
    assert "FFmpegExtractAudio" not in pp_keys
    assert "FFmpegMetadata" in pp_keys


@pytest.mark.django_db
def test_mp3_cbr_modes_ydl_opts():
    """Verify Mode B (320), Mode C (256), Mode D (192) configure target bitrates."""
    for qual, expected_br in [("mp3_320", "320"), ("mp3_256", "256"), ("mp3_192", "192")]:
        job = DownloadJob(
            url="https://www.youtube.com/watch?v=dummy123",
            audio_only=True,
            output_format="mp3",
            output_quality=qual,
        )
        opts = _build_ydl_opts(job, Path("/tmp"), lambda: False)
        assert opts["format"] == "bestaudio/best"
        extract_pp = next((p for p in opts["postprocessors"] if p.get("key") == "FFmpegExtractAudio"), None)
        assert extract_pp is not None
        assert extract_pp["preferredcodec"] == "mp3"
        assert extract_pp["preferredquality"] == expected_br


@pytest.mark.django_db
def test_mp3_vbr_mode_ydl_opts():
    """Verify Mode E (MP3 VBR High Quality) configures -q:a 2."""
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=dummy123",
        audio_only=True,
        output_format="mp3",
        output_quality="mp3_vbr_high",
    )
    opts = _build_ydl_opts(job, Path("/tmp"), lambda: False)
    assert opts["format"] == "bestaudio/best"
    extract_pp = next((p for p in opts["postprocessors"] if p.get("key") == "FFmpegExtractAudio"), None)
    assert extract_pp is not None
    assert extract_pp["preferredcodec"] == "mp3"
    assert opts.get("postprocessor_args", {}).get("ExtractAudio") == ["-q:a", "2"]


@pytest.mark.django_db
def test_legacy_quality_presets_compatibility():
    """Verify legacy 'best', 'high', 'medium' retain their intended bitrates."""
    legacy_cases = [
        ("best", "320"),
        ("high", "256"),
        ("medium", "192"),
    ]
    for legacy_val, expected_br in legacy_cases:
        job = DownloadJob(
            url="https://www.youtube.com/watch?v=dummy123",
            audio_only=True,
            output_format="mp3",
            output_quality=legacy_val,
        )
        opts = _build_ydl_opts(job, Path("/tmp"), lambda: False)
        extract_pp = next((p for p in opts["postprocessors"] if p.get("key") == "FFmpegExtractAudio"), None)
        assert extract_pp is not None
        assert extract_pp["preferredquality"] == expected_br


@pytest.mark.django_db
def test_app_settings_defaults_and_legacy_resolution():
    """Verify default settings and resolution of legacy SQLite values."""
    settings_obj = AppSettings.get()
    assert settings_obj.default_audio_format in ("original", "mp3")

    # Set legacy SQLite value
    settings_obj.default_audio_quality = "high"
    assert settings_obj.resolved_audio_quality == "mp3_256"

    settings_obj.default_audio_quality = "best"
    assert settings_obj.resolved_audio_quality == "mp3_320"

    settings_obj.default_audio_quality = "original"
    assert settings_obj.resolved_audio_quality == "original"


@pytest.mark.django_db
def test_download_job_metadata_properties():
    """Verify DownloadJob properties display actual vs target vs source bitrates."""
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=dummy123",
        output_format="original",
        output_quality="original",
        extra_metadata={
            "source_bitrate": 130,
            "output_info": {
                "format_name": "webm",
                "audio_codec": "opus",
                "audio_bitrate": 131000,
                "sample_rate": 48000,
                "channels": 2,
            },
        },
    )
    assert job.actual_codec == "opus"
    assert job.actual_container == "webm"
    assert job.actual_bitrate_display == "131 kbps"
    assert job.source_bitrate_display == "130 kbps"
    assert job.target_bitrate_display == "N/A (Source preserved)"
    assert "OPUS" in job.audio_summary_display
    assert "48000 Hz" in job.audio_summary_display


@pytest.mark.django_db
def test_conversion_vbr_and_cbr():
    """Verify local video-to-audio conversion commands."""
    vbr_job = ConversionJob(output_format="mp3", output_quality="mp3_vbr_high")
    cmd_vbr = _build_ffmpeg_cmd("ffmpeg", Path("in.mp4"), Path("out.mp3"), vbr_job)
    assert "-q:a" in cmd_vbr and "2" in cmd_vbr

    cbr_job = ConversionJob(output_format="mp3", output_quality="mp3_320")
    cmd_cbr = _build_ffmpeg_cmd("ffmpeg", Path("in.mp4"), Path("out.mp3"), cbr_job)
    assert "-b:a" in cmd_cbr and "320k" in cmd_cbr


def test_validator_incompatible_combinations():
    """Verify validator rejects incompatible format/quality combinations."""
    # Original format with MP3-only 320 kbps
    with pytest.raises(ValidationError):
        validate_audio_quality("mp3_320", "original")

    # MP3 format with Original quality
    with pytest.raises(ValidationError):
        validate_audio_quality("original", "mp3")

    # Valid combinations should pass
    assert validate_audio_quality("original", "original") == "original"
    assert validate_audio_quality("mp3_320", "mp3") == "mp3_320"
    assert validate_audio_quality("mp3_vbr_high", "mp3") == "mp3_vbr_high"


@pytest.mark.django_db
def test_video_download_mode():
    """Verify video downloads preserve video stream format options."""
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=dummy123",
        audio_only=False,
    )
    opts = _build_ydl_opts(job, Path("/tmp"), lambda: False)
    assert opts["format"] == "bestvideo+bestaudio/best"
    assert opts["merge_output_format"] == "mp4"


@pytest.mark.django_db
def test_home_page_single_primary_action():
    """Verify home page loads cleanly without duplicate download buttons."""
    client = Client()
    resp = client.get(reverse("dashboard"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "MediaFlow" in content
    assert "Download media" in content
    assert "Review media" in content
    assert "Start download" in content


def test_quality_choices_no_legacy_clutter():
    """Verify dropdown choices only present clean modern quality modes without legacy clutter."""
    from downloader.forms import _quality_choices
    choices = _quality_choices()
    keys = [k for k, _ in choices]
    labels = [l for _, l in choices]
    assert keys == ["original", "mp3_320", "mp3_256", "mp3_192", "mp3_vbr_high"]
    for label in labels:
        assert "legacy" not in label.lower()


@pytest.mark.django_db
def test_playlist_view_url_prepopulation():
    """Verify playlist view pre-populates the URL from query parameters."""
    client = Client()
    url = "https://www.youtube.com/playlist?list=PL1234567890"
    resp = client.get(f"{reverse('playlist')}?url={url}")
    assert resp.status_code == 200
    content = resp.content.decode()
    assert url in content
    assert "inspectPlaylistBtn" in content


@pytest.mark.django_db
def test_playlist_view_post_missing_action_returns_json_error():
    """Verify that posting to /playlist/ without an action returns 400 JSON error rather than 500 UnboundLocalError."""
    client = Client()
    resp = client.post(reverse("playlist"), {})
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert "Invalid or missing action" in data["error"]


@pytest.mark.django_db
def test_playlist_view_post_json_download():
    """Verify JSON body with action='download' is properly parsed and queues playlist job."""
    client = Client()
    payload = {
        "action": "download",
        "url": "https://www.youtube.com/playlist?list=PL1234567890",
        "playlist_title": "Test Playlist",
        "selected_indices": [1],
        "entries": [
            {
                "index": 1,
                "url": "https://www.youtube.com/watch?v=track1",
                "title": "Track 1",
                "uploader": "Artist",
                "duration": 180,
            }
        ],
        "output_format": "mp3",
        "output_quality": "mp3_320",
    }
    with patch("downloader.views.get_job_manager") as mock_mgr_fn:
        mock_mgr = MagicMock()
        mock_mgr_fn.return_value = mock_mgr

        resp = client.post(
            reverse("playlist"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "job_id" in data
        mock_mgr.submit_download.assert_called_once()


@pytest.mark.django_db
def test_app_settings_normalizes_legacy_quality():
    """Verify AppSettings.get() maps legacy 'high' to 'mp3_320'."""
    from downloader.models import AppSettings
    # Force legacy quality into DB row
    AppSettings.objects.update_or_create(pk=1, defaults={"default_audio_quality": "high"})
    cfg = AppSettings.get()
    assert cfg.default_audio_quality == "mp3_320"


@pytest.mark.django_db
def test_forms_accept_and_normalize_legacy_quality():
    """Verify forms gracefully accept legacy quality values."""
    from downloader.forms import DownloadForm, PlaylistForm
    form = DownloadForm({
        "url": "https://www.youtube.com/watch?v=test1234567",
        "output_format": "mp3",
        "output_quality": "high",
    })
    assert form.is_valid()
    assert form.cleaned_data["output_quality"] == "mp3_320"

    pl_form = PlaylistForm({
        "url": "https://www.youtube.com/playlist?list=PL1234567890",
        "output_format": "mp3",
        "output_quality": "high",
    })
    assert pl_form.is_valid()
    assert pl_form.cleaned_data["output_quality"] == "mp3_320"

