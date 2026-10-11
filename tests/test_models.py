"""Tests for database models."""

import pytest
from downloader.models import (
    AppSettings,
    AudioFormat,
    ConversionJob,
    DownloadJob,
    JobStatus,
    JobType,
    PlaylistItem,
)


@pytest.mark.django_db
def test_app_settings_singleton():
    cfg1 = AppSettings.get()
    cfg2 = AppSettings.get()
    assert cfg1.pk == cfg2.pk == 1
    assert cfg1.download_dir_path.exists()
    assert str(cfg1) == "Application Settings"


@pytest.mark.django_db
def test_download_job_model():
    job = DownloadJob.objects.create(
        url="https://www.youtube.com/watch?v=test",
        title="Sample Video",
        duration=125,
        file_size=1024 * 1024 * 4,  # 4 MB
        output_path="D:/Downloads/Sample Video.mp3",
        status=JobStatus.RUNNING,
    )

    assert str(job) == "[running] Sample Video"
    assert job.duration_display == "2:05"
    assert "4.0 MB" in job.file_size_display
    assert job.is_active is True
    assert job.output_filename == "Sample Video.mp3"

    job.status = JobStatus.COMPLETED
    job.save()
    assert job.is_active is False


@pytest.mark.django_db
def test_playlist_item_model():
    job = DownloadJob.objects.create(
        job_type=JobType.PLAYLIST,
        url="https://www.youtube.com/playlist?list=test",
        title="Sample Playlist",
    )
    item = PlaylistItem.objects.create(
        playlist_job=job,
        index=1,
        url="https://www.youtube.com/watch?v=track1",
        title="Track 1",
        duration=3665,
    )

    assert str(item) == "#1: Track 1"
    assert item.duration_display == "1:01:05"


@pytest.mark.django_db
def test_conversion_job_model():
    conv = ConversionJob.objects.create(
        input_path="C:/Media/input.mp4",
        input_filename="input.mp4",
        output_format=AudioFormat.MP3,
        output_path="C:/Media/input.mp3",
        status=JobStatus.QUEUED,
    )

    assert str(conv) == "[queued] input.mp4 → mp3"
    assert conv.is_active is True
    assert conv.output_filename == "input.mp3"
