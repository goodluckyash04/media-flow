"""Tests for Django views and API endpoints."""

import json
from unittest.mock import patch
import pytest
from django.test import Client
from django.urls import reverse

from downloader.models import AppSettings, DownloadJob, JobStatus


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_dashboard_view(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    assert "MediaFlow" in response.content.decode()


@pytest.mark.django_db
def test_download_new_view(client):
    response = client.get(reverse("download"))
    assert response.status_code == 200
    assert "New Download" in response.content.decode()


@pytest.mark.django_db
def test_inspect_url_view(client):
    with patch("downloader.services.metadata_service.fetch_media_info") as mock_fetch:
        mock_fetch.return_value = {
            "title": "Inspected Media",
            "uploader": "Channel Name",
            "duration": 180,
            "thumbnail": "https://example.com/thumb.jpg",
            "extractor": "youtube",
        }
        response = client.post(
            reverse("inspect_url"),
            data=json.dumps({"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["info"]["title"] == "Inspected Media"


@pytest.mark.django_db
def test_playlist_view(client):
    response = client.get(reverse("playlist"))
    assert response.status_code == 200
    assert "Playlist" in response.content.decode()


@pytest.mark.django_db
def test_converter_view(client):
    response = client.get(reverse("converter"))
    assert response.status_code == 200
    assert "Converter" in response.content.decode()


@pytest.mark.django_db
def test_queue_view_and_status(client):
    response = client.get(reverse("queue"))
    assert response.status_code == 200

    status_resp = client.get(reverse("queue_status"))
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["ok"] is True
    assert "downloads" in status_data
    assert "conversions" in status_data


@pytest.mark.django_db
def test_library_view(client):
    response = client.get(reverse("library"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_settings_view(client):
    response = client.get(reverse("settings"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_job_progress_api(client):
    job = DownloadJob.objects.create(
        url="https://example.com/media",
        title="Sample Video",
        status=JobStatus.RUNNING,
        progress_pct=42.5,
    )
    url = reverse("job_progress", kwargs={"job_id": str(job.id)})
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["job"]["progress_pct"] == 42.5
    assert data["job"]["status"] == "running"


@pytest.mark.django_db
def test_cancel_download_api(client):
    job = DownloadJob.objects.create(
        url="https://example.com/media",
        status=JobStatus.RUNNING,
    )
    url = reverse("cancel_download", kwargs={"job_id": str(job.id)})
    response = client.post(url)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


@pytest.mark.django_db
def test_delete_history_record_api(client):
    job = DownloadJob.objects.create(
        url="https://example.com/media",
        status=JobStatus.COMPLETED,
    )
    url = reverse("delete_record", kwargs={"job_id": str(job.id)})
    response = client.post(
        url,
        data=json.dumps({"delete_file": False}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert not DownloadJob.objects.filter(pk=job.id).exists()


@pytest.mark.django_db
def test_playlist_inspect_json(client):
    with patch("downloader.services.metadata_service.fetch_playlist_info") as mock_fetch:
        mock_fetch.return_value = {
            "title": "Cool Playlist",
            "uploader": "Cool Curator",
            "webpage_url": "https://www.youtube.com/playlist?list=PL123",
            "thumbnail": "https://example.com/thumb.jpg",
            "entry_count": 2,
            "entries": [
                {"index": 1, "title": "Track 1", "url": "https://www.youtube.com/watch?v=1", "thumbnail": ""},
                {"index": 2, "title": "Track 2", "url": "https://www.youtube.com/watch?v=2", "thumbnail": ""},
            ],
        }
        response = client.post(
            reverse("playlist"),
            data=json.dumps({"action": "inspect", "url": "https://www.youtube.com/playlist?list=PL123"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["info"]["title"] == "Cool Playlist"
        assert len(data["info"]["entries"]) == 2


@pytest.mark.django_db
def test_playlist_inspect_form_data(client):
    """Ensure form POST does not raise RawPostDataException and successfully inspects."""
    with patch("downloader.services.metadata_service.fetch_playlist_info") as mock_fetch:
        mock_fetch.return_value = {
            "title": "Form Playlist",
            "uploader": "Form Curator",
            "webpage_url": "https://www.youtube.com/playlist?list=PL456",
            "thumbnail": "https://example.com/thumb.jpg",
            "entry_count": 1,
            "entries": [
                {"index": 1, "title": "Track 1", "url": "https://www.youtube.com/watch?v=1", "thumbnail": ""},
            ],
        }
        response = client.post(
            reverse("playlist"),
            data={"action": "inspect", "url": "https://www.youtube.com/playlist?list=PL456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["info"]["title"] == "Form Playlist"


@pytest.mark.django_db
def test_playlist_inspect_defaults_action(client):
    """When action is omitted but url is supplied, default to inspect."""
    with patch("downloader.services.metadata_service.fetch_playlist_info") as mock_fetch:
        mock_fetch.return_value = {
            "title": "Default Action Playlist",
            "uploader": "Default Curator",
            "webpage_url": "https://www.youtube.com/playlist?list=PL789",
            "thumbnail": "",
            "entry_count": 0,
            "entries": [],
        }
        response = client.post(
            reverse("playlist"),
            data=json.dumps({"url": "https://www.youtube.com/playlist?list=PL789"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["info"]["title"] == "Default Action Playlist"

