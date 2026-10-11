"""
Views for the media downloader application.

All views follow the thin-view pattern:
  - Request/response handling and form validation only.
  - Business logic delegated to services.
  - Long-running work submitted to the job manager.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from downloader.forms import ConversionForm, DownloadForm, PlaylistForm, SettingsForm
from downloader.models import (
    AppSettings,
    AudioFormat,
    ConversionJob,
    DownloadJob,
    JobStatus,
    JobType,
    PlaylistItem,
)
from downloader.workers.job_manager import get_job_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


def _json_ok(data: Dict = None) -> JsonResponse:
    payload = {"ok": True}
    if data:
        payload.update(data)
    return JsonResponse(payload)


def _get_app_settings() -> AppSettings:
    return AppSettings.get()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard(request):
    """Main dashboard: quick stats and recent activity."""
    active_downloads = DownloadJob.objects.filter(
        status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
    ).order_by("-created_at")[:5]

    recent_downloads = DownloadJob.objects.exclude(
        status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
    ).order_by("-created_at")[:10]

    active_conversions = ConversionJob.objects.filter(
        status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
    ).order_by("-created_at")[:5]

    stats = {
        "active": DownloadJob.objects.filter(
            status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
        ).count(),
        "completed": DownloadJob.objects.filter(status=JobStatus.COMPLETED).count(),
        "failed": DownloadJob.objects.filter(status=JobStatus.FAILED).count(),
        "conversions_active": ConversionJob.objects.filter(
            status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
        ).count(),
        "conversions_done": ConversionJob.objects.filter(
            status=JobStatus.COMPLETED
        ).count(),
    }

    try:
        app_cfg = _get_app_settings()
        download_dir = app_cfg.download_dir_path
        from downloader.utils.file_utils import get_directory_size, human_readable_size
        stats["storage"] = human_readable_size(get_directory_size(download_dir))
        stats["download_dir"] = str(download_dir)
    except Exception:
        stats["storage"] = "N/A"
        stats["download_dir"] = ""

    return render(
        request,
        "downloader/dashboard.html",
        {
            "active_downloads": active_downloads,
            "recent_downloads": recent_downloads,
            "active_conversions": active_conversions,
            "stats": stats,
        },
    )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_new(request):
    """Show the new download form and handle inspection + submission."""
    app_cfg = _get_app_settings()

    if request.method == "POST":
        form = DownloadForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            if data.get("inspect_only"):
                # Return metadata as JSON for the preview panel
                return _inspect_url(data["url"])

            # Create and queue the job
            job = DownloadJob.objects.create(
                url=data["url"],
                audio_only=data.get("audio_only", True),
                output_format=data["output_format"],
                output_quality=data["output_quality"],
                output_dir=data.get("output_dir") or str(app_cfg.download_dir_path),
                filename_template=app_cfg.filename_template,
                status=JobStatus.QUEUED,
                stage="Queued",
            )

            mgr = get_job_manager()
            mgr.submit_download(str(job.id))

            messages.success(request, f"Download queued successfully.")
            return redirect("queue")
    else:
        form = DownloadForm(
            initial={
                "output_format": app_cfg.default_audio_format,
                "output_quality": app_cfg.default_audio_quality,
                "audio_only": True,
            }
        )

    return render(
        request,
        "downloader/download.html",
        {
            "form": form,
            "app_cfg": app_cfg,
            "quality_presets_json": json.dumps(settings.AUDIO_QUALITY_PRESETS),
        },
    )


def _inspect_url(url: str) -> JsonResponse:
    """Fetch media metadata via yt-dlp and return as JSON."""
    try:
        from downloader.services.metadata_service import fetch_media_info
        info = fetch_media_info(url)
        return _json_ok({"info": info})
    except Exception as exc:
        logger.warning("Metadata inspection failed for %s: %s", url, exc)
        return _json_error(str(exc))


@require_POST
def inspect_url(request):
    """AJAX endpoint: fetch metadata for a URL without downloading."""
    try:
        body = json.loads(request.body)
        url = body.get("url", "").strip()
    except Exception:
        return _json_error("Invalid request body.")

    from downloader.utils.validators import validate_url
    from django.core.exceptions import ValidationError
    try:
        url = validate_url(url)
    except ValidationError as exc:
        return _json_error(str(exc))

    return _inspect_url(url)


# ---------------------------------------------------------------------------
# Playlist
# ---------------------------------------------------------------------------

def playlist_view(request):
    """Show playlist inspection form and handle playlist job submission."""
    app_cfg = _get_app_settings()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "inspect":
            form = PlaylistForm(request.POST)
            if form.is_valid():
                url = form.cleaned_data["url"]
                try:
                    from downloader.services.metadata_service import fetch_playlist_info
                    info = fetch_playlist_info(url)
                    return _json_ok({"info": info})
                except Exception as exc:
                    return _json_error(str(exc))
            return _json_error(str(form.errors))

        elif action == "download":
            # Parse the playlist download request
            try:
                body = json.loads(request.body)
            except Exception:
                body = request.POST.dict()

            url = body.get("url", "")
            selected_indices = body.get("selected_indices", [])
            entries = body.get("entries", [])
            output_format = body.get("output_format", app_cfg.default_audio_format)
            output_quality = body.get("output_quality", app_cfg.default_audio_quality)
            output_dir = body.get("output_dir", "") or str(app_cfg.download_dir_path)
            playlist_title = body.get("playlist_title", "playlist")

            if not url or not entries:
                return _json_error("URL and track entries are required.")

            # Create parent playlist job
            parent = DownloadJob.objects.create(
                url=url,
                title=playlist_title,
                job_type=JobType.PLAYLIST,
                audio_only=True,
                output_format=output_format,
                output_quality=output_quality,
                output_dir=output_dir,
                status=JobStatus.QUEUED,
                stage="Queued",
            )

            # Create playlist items
            selected_set = set(int(i) for i in selected_indices if str(i).isdigit())
            for entry in entries:
                idx = int(entry.get("index", 0))
                PlaylistItem.objects.create(
                    playlist_job=parent,
                    index=idx,
                    url=entry.get("url", ""),
                    title=entry.get("title", f"Track {idx}"),
                    uploader=entry.get("uploader", ""),
                    duration=entry.get("duration"),
                    thumbnail_url=entry.get("thumbnail", ""),
                    selected=(idx in selected_set) if selected_set else True,
                )

            get_job_manager().submit_download(str(parent.id))
            return _json_ok({"job_id": str(parent.id)})

    else:
        form = PlaylistForm(
            initial={
                "output_format": app_cfg.default_audio_format,
                "output_quality": app_cfg.default_audio_quality,
            }
        )

    return render(request, "downloader/playlist.html", {"form": form, "app_cfg": app_cfg})


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------

def converter_view(request):
    """Show the local file converter and handle conversion job submission."""
    app_cfg = _get_app_settings()

    from downloader.services.conversion_service import detect_ffmpeg
    ffmpeg_ok, ffmpeg_ver = detect_ffmpeg(app_cfg.resolved_ffmpeg_path)

    if request.method == "POST":
        form = ConversionForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            files = data["input_files"]
            output_dir = data.get("output_dir", "")
            output_format = data["output_format"]
            output_quality = data["output_quality"]

            if not ffmpeg_ok:
                messages.error(
                    request,
                    "FFmpeg is not available. Please install it and configure the path in Settings.",
                )
                return render(
                    request,
                    "downloader/converter.html",
                    {"form": form, "ffmpeg_ok": ffmpeg_ok, "ffmpeg_ver": ffmpeg_ver, "app_cfg": app_cfg},
                )

            job_ids = []
            for file_path in files:
                p = Path(file_path)
                job = ConversionJob.objects.create(
                    input_path=str(p),
                    input_filename=p.name,
                    input_size=p.stat().st_size if p.exists() else None,
                    output_format=output_format,
                    output_quality=output_quality,
                    output_dir=output_dir or str(p.parent),
                    status=JobStatus.QUEUED,
                    stage="Queued",
                )
                get_job_manager().submit_conversion(str(job.id))
                job_ids.append(str(job.id))

            messages.success(
                request,
                f"{len(job_ids)} conversion job(s) queued.",
            )
            return redirect("queue")
    else:
        form = ConversionForm(
            initial={
                "output_format": app_cfg.default_audio_format,
                "output_quality": app_cfg.default_audio_quality,
            }
        )

    return render(
        request,
        "downloader/converter.html",
        {
            "form": form,
            "ffmpeg_ok": ffmpeg_ok,
            "ffmpeg_ver": ffmpeg_ver,
            "app_cfg": app_cfg,
            "quality_presets_json": json.dumps(settings.AUDIO_QUALITY_PRESETS),
        },
    )


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------

def queue_view(request):
    """Show the download and conversion queue."""
    downloads = DownloadJob.objects.all().order_by("-created_at")[:100]
    conversions = ConversionJob.objects.all().order_by("-created_at")[:50]

    return render(
        request,
        "downloader/queue.html",
        {
            "downloads": downloads,
            "conversions": conversions,
        },
    )


# ---------------------------------------------------------------------------
# Progress API
# ---------------------------------------------------------------------------

def job_progress(request, job_id):
    """Return current progress for a download job as JSON."""
    try:
        job = DownloadJob.objects.get(pk=job_id)
    except (DownloadJob.DoesNotExist, Exception):
        return _json_error("Job not found.", status=404)

    items = []
    if job.job_type == JobType.PLAYLIST:
        for item in job.playlist_items.all():
            items.append(
                {
                    "id": str(item.id),
                    "index": item.index,
                    "title": item.title,
                    "status": item.status,
                    "progress_pct": item.progress_pct,
                    "selected": item.selected,
                    "error": item.error_message,
                    "output_path": item.output_path,
                }
            )

    return _json_ok(
        {
            "job": {
                "id": str(job.id),
                "status": job.status,
                "progress_pct": job.progress_pct,
                "speed": job.speed,
                "eta": job.eta,
                "stage": job.stage,
                "title": job.title,
                "error": job.error_message,
                "output_path": job.output_path,
                "output_filename": job.output_filename,
            },
            "items": items,
        }
    )


def conversion_progress(request, job_id):
    """Return current progress for a conversion job as JSON."""
    try:
        job = ConversionJob.objects.get(pk=job_id)
    except (ConversionJob.DoesNotExist, Exception):
        return _json_error("Conversion job not found.", status=404)

    return _json_ok(
        {
            "job": {
                "id": str(job.id),
                "status": job.status,
                "progress_pct": job.progress_pct,
                "stage": job.stage,
                "input_filename": job.input_filename,
                "output_format": job.output_format,
                "error": job.error_message,
                "output_path": job.output_path,
                "output_filename": job.output_filename,
            }
        }
    )


def queue_status(request):
    """Return summary of all active jobs and recently finished jobs for queue/dashboard polling."""
    import datetime
    from django.db.models import Q

    recent_cutoff = timezone.now() - datetime.timedelta(seconds=60)

    downloads = DownloadJob.objects.filter(
        Q(status__in=[JobStatus.QUEUED, JobStatus.RUNNING]) |
        Q(completed_at__gte=recent_cutoff)
    ).values("id", "title", "status", "progress_pct", "speed", "eta", "stage", "job_type", "error_message", "output_path")

    conversions = ConversionJob.objects.filter(
        Q(status__in=[JobStatus.QUEUED, JobStatus.RUNNING]) |
        Q(completed_at__gte=recent_cutoff)
    ).values("id", "input_filename", "output_format", "status", "progress_pct", "stage", "error_message", "output_path")

    active_dl_count = DownloadJob.objects.filter(
        status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
    ).count()
    active_conv_count = ConversionJob.objects.filter(
        status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
    ).count()

    return _json_ok(
        {
            "downloads": [
                {**d, "id": str(d["id"])} for d in downloads
            ],
            "conversions": [
                {**c, "id": str(c["id"])} for c in conversions
            ],
            "active_downloads_count": active_dl_count,
            "active_conversions_count": active_conv_count,
            "active_total": active_dl_count + active_conv_count,
        }
    )


# ---------------------------------------------------------------------------
# Cancel / Retry / Delete actions
# ---------------------------------------------------------------------------

@require_POST
def cancel_download(request, job_id):
    """Cancel a download job."""
    try:
        job = get_object_or_404(DownloadJob, pk=job_id)
        mgr = get_job_manager()
        cancelled = mgr.cancel_job(str(job.id))
        if not cancelled:
            # Not in executor – mark directly
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                job.status = JobStatus.CANCELLED
                job.completed_at = timezone.now()
                job.stage = "Cancelled"
                job.save(update_fields=["status", "completed_at", "stage"])
        return _json_ok({"message": "Cancel signal sent."})
    except Exception as exc:
        return _json_error(str(exc))


@require_POST
def retry_download(request, job_id):
    """Reset a failed/cancelled download job and requeue it."""
    job = get_object_or_404(DownloadJob, pk=job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        return _json_error("Only failed or cancelled jobs can be retried.")

    job.status = JobStatus.QUEUED
    job.progress_pct = 0.0
    job.error_message = ""
    job.stage = "Queued (retry)"
    job.started_at = None
    job.completed_at = None
    job.save()

    get_job_manager().submit_download(str(job.id))
    return _json_ok({"message": "Job requeued."})


@require_POST
def cancel_conversion(request, job_id):
    """Cancel a conversion job."""
    try:
        job = get_object_or_404(ConversionJob, pk=job_id)
        mgr = get_job_manager()
        cancelled = mgr.cancel_job(str(job.id))
        if not cancelled:
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                job.status = JobStatus.CANCELLED
                job.completed_at = timezone.now()
                job.stage = "Cancelled"
                job.save(update_fields=["status", "completed_at", "stage"])
        return _json_ok({"message": "Cancel signal sent."})
    except Exception as exc:
        return _json_error(str(exc))


@require_POST
def retry_conversion(request, job_id):
    """Reset a failed/cancelled conversion job and requeue it."""
    job = get_object_or_404(ConversionJob, pk=job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        return _json_error("Only failed or cancelled jobs can be retried.")

    job.status = JobStatus.QUEUED
    job.progress_pct = 0.0
    job.error_message = ""
    job.stage = "Queued (retry)"
    job.started_at = None
    job.completed_at = None
    job.save()

    get_job_manager().submit_conversion(str(job.id))
    return _json_ok({"message": "Conversion requeued."})


# ---------------------------------------------------------------------------
# Library / History
# ---------------------------------------------------------------------------

def library_view(request):
    """Show all past and active jobs with search/filter."""
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "")
    job_type = request.GET.get("type", "download")

    if job_type == "conversion":
        qs = ConversionJob.objects.all().order_by("-created_at")
        if q:
            qs = qs.filter(input_filename__icontains=q)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return render(
            request,
            "downloader/library.html",
            {
                "jobs": qs[:200],
                "q": q,
                "status_filter": status_filter,
                "job_type": job_type,
                "status_choices": JobStatus.choices,
            },
        )

    qs = DownloadJob.objects.all().order_by("-created_at")
    if q:
        qs = qs.filter(title__icontains=q) | qs.filter(url__icontains=q)
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(
        request,
        "downloader/library.html",
        {
            "jobs": qs[:200],
            "q": q,
            "status_filter": status_filter,
            "job_type": job_type,
            "status_choices": JobStatus.choices,
        },
    )


@require_POST
def delete_history_record(request, job_id):
    """Delete a job history record (NOT the output file)."""
    try:
        body = json.loads(request.body) if request.body else {}
        delete_file = body.get("delete_file", False)
    except Exception:
        delete_file = False

    # Try download job first
    try:
        job = DownloadJob.objects.get(pk=job_id)
        if delete_file and job.output_path:
            output = Path(job.output_path)
            if output.exists() and output.is_file():
                output.unlink()
        job.delete()
        return _json_ok({"message": "Record deleted."})
    except DownloadJob.DoesNotExist:
        pass

    # Try conversion job
    try:
        job = ConversionJob.objects.get(pk=job_id)
        if delete_file and job.output_path:
            output = Path(job.output_path)
            if output.exists() and output.is_file():
                output.unlink()
        job.delete()
        return _json_ok({"message": "Record deleted."})
    except ConversionJob.DoesNotExist:
        pass

    return _json_error("Record not found.", status=404)


def open_output_folder(request, job_id):
    """Open the containing folder of a completed job's output file (Windows)."""
    # Try download job
    output_path = None
    try:
        job = DownloadJob.objects.get(pk=job_id)
        output_path = job.output_path
    except DownloadJob.DoesNotExist:
        try:
            job = ConversionJob.objects.get(pk=job_id)
            output_path = job.output_path
        except ConversionJob.DoesNotExist:
            return _json_error("Job not found.", status=404)

    if not output_path:
        return _json_error("No output file recorded for this job.")

    p = Path(output_path)
    folder = p.parent if p.is_file() else p

    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return _json_ok({"folder": str(folder)})
    except Exception as exc:
        return _json_error(f"Could not open folder: {exc}")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def settings_view(request):
    """Application settings page."""
    app_cfg = _get_app_settings()

    from downloader.services.conversion_service import detect_ffmpeg, detect_ffprobe
    ffmpeg_ok, ffmpeg_ver = detect_ffmpeg(app_cfg.resolved_ffmpeg_path)
    ffprobe_ok, ffprobe_ver = detect_ffprobe(app_cfg.resolved_ffprobe_path)

    # yt-dlp version
    try:
        import yt_dlp
        ytdlp_ver = yt_dlp.version.__version__
    except Exception:
        ytdlp_ver = "unknown"

    if request.method == "POST":
        form = SettingsForm(request.POST, instance=app_cfg)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved successfully.")
            return redirect("settings")
    else:
        form = SettingsForm(instance=app_cfg)

    return render(
        request,
        "downloader/settings.html",
        {
            "form": form,
            "ffmpeg_ok": ffmpeg_ok,
            "ffmpeg_ver": ffmpeg_ver,
            "ffprobe_ok": ffprobe_ok,
            "ffprobe_ver": ffprobe_ver,
            "ytdlp_ver": ytdlp_ver,
            "app_cfg": app_cfg,
        },
    )


@require_POST
def update_ytdlp(request):
    """Trigger a yt-dlp self-update."""
    try:
        result = subprocess.run(
            ["yt-dlp", "-U"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        return _json_ok({"output": output[:2000]})
    except Exception as exc:
        return _json_error(str(exc))


# ---------------------------------------------------------------------------
# Spotify
# ---------------------------------------------------------------------------

@require_POST
def spotify_inspect(request):
    """Inspect a Spotify URL and return track/playlist metadata."""
    try:
        body = json.loads(request.body)
        url = body.get("url", "").strip()
    except Exception:
        return _json_error("Invalid request body.")

    if not url:
        return _json_error("URL is required.")

    from downloader.services.spotify_service import (
        SpotifyServiceUnavailable,
        fetch_spotify_playlist,
        fetch_spotify_track,
        is_spotify_url,
    )

    if not is_spotify_url(url):
        return _json_error("Not a valid Spotify URL.")

    try:
        if "/track/" in url or ":track:" in url:
            info = fetch_spotify_track(url)
            return _json_ok({"type": "track", "info": info})
        elif "/playlist/" in url or ":playlist:" in url:
            info = fetch_spotify_playlist(url)
            return _json_ok({"type": "playlist", "info": info})
        else:
            return _json_error("Unsupported Spotify URL type. Only tracks and playlists are supported.")
    except SpotifyServiceUnavailable as exc:
        return _json_error(str(exc))
    except Exception as exc:
        logger.exception("Spotify inspect failed for %s", url)
        return _json_error(str(exc))


# ---------------------------------------------------------------------------
# Error pages
# ---------------------------------------------------------------------------

def error_400(request, exception=None):
    return render(request, "downloader/error.html", {"code": 400, "message": "Bad Request"}, status=400)


def error_403(request, exception=None):
    return render(request, "downloader/error.html", {"code": 403, "message": "Forbidden"}, status=403)


def error_404(request, exception=None):
    return render(request, "downloader/error.html", {"code": 404, "message": "Page Not Found"}, status=404)


def error_500(request):
    return render(request, "downloader/error.html", {"code": 500, "message": "Internal Server Error"}, status=500)
