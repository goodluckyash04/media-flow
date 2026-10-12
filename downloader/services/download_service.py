"""
Download service: executes yt-dlp downloads and reports progress
back to the job model via thread-safe database updates.

This module is called by the background job manager and must NOT
run inside a Django request/response cycle.
"""

import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yt_dlp
from django.conf import settings
from django.utils import timezone

from downloader.models import DownloadJob, JobStatus, PlaylistItem
from downloader.utils.file_utils import safe_output_path

logger = logging.getLogger(__name__)

# Lock to serialise brief DB writes per job
_db_lock = threading.Lock()


def _save_job_fields(job_id: str, **kwargs):
    """Thread-safe partial update of a DownloadJob."""
    with _db_lock:
        DownloadJob.objects.filter(pk=job_id).update(**kwargs)


def _save_item_fields(item_id: str, **kwargs):
    """Thread-safe partial update of a PlaylistItem."""
    with _db_lock:
        PlaylistItem.objects.filter(pk=item_id).update(**kwargs)


# ---------------------------------------------------------------------------
# Progress hook
# ---------------------------------------------------------------------------

class _ProgressHook:
    """Translates yt-dlp progress callbacks into DB updates."""

    def __init__(self, job_id: str, cancel_check: Callable[[], bool]):
        self.job_id = job_id
        self.cancel_check = cancel_check
        self._last_pct = 0.0

    def __call__(self, d: Dict[str, Any]):
        if self.cancel_check():
            raise yt_dlp.utils.DownloadError("Job cancelled by user")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            pct = (downloaded / total * 100.0) if total else 0.0

            # Rate-limit DB writes (only update if >1% change)
            if abs(pct - self._last_pct) >= 1.0 or pct >= 99.0:
                self._last_pct = pct
                speed = d.get("_speed_str", "").strip()
                eta = d.get("_eta_str", "").strip()
                _save_job_fields(
                    self.job_id,
                    progress_pct=round(pct, 1),
                    speed=speed,
                    eta=eta,
                    stage="Downloading",
                )

        elif status == "finished":
            _save_job_fields(
                self.job_id,
                progress_pct=95.0,
                stage="Post-processing",
                speed="",
                eta="",
            )

        elif status == "error":
            _save_job_fields(self.job_id, stage="Error during download")


# ---------------------------------------------------------------------------
# Single-media download
# ---------------------------------------------------------------------------

def run_download_job(job_id: str, cancel_check: Callable[[], bool]):
    """
    Execute a single-media download job.
    Updates the DownloadJob row throughout.
    """
    try:
        job = DownloadJob.objects.get(pk=job_id)
    except DownloadJob.DoesNotExist:
        logger.error("DownloadJob %s not found", job_id)
        return

    _save_job_fields(
        job_id,
        status=JobStatus.RUNNING,
        started_at=timezone.now(),
        stage="Initialising",
    )

    try:
        output_dir = Path(job.output_dir) if job.output_dir else settings.DEFAULT_DOWNLOAD_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        opts = _build_ydl_opts(job, output_dir, cancel_check)

        logger.info("Starting download for job %s: %s", job_id, job.url)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(job.url, download=True)

        # Determine the actual output file
        output_path = _find_output_file(info, output_dir, opts)

        output_info = {}
        if output_path and output_path.exists():
            from downloader.services.conversion_service import probe_file
            output_info = probe_file(output_path)

        meta = dict(job.extra_metadata or {})
        if output_info:
            meta["output_info"] = output_info
        if info:
            abr = info.get("abr")
            if abr:
                meta["source_bitrate"] = abr

        _save_job_fields(
            job_id,
            status=JobStatus.COMPLETED,
            completed_at=timezone.now(),
            progress_pct=100.0,
            stage="Complete",
            output_path=str(output_path) if output_path else "",
            file_size=output_path.stat().st_size if output_path and output_path.exists() else None,
            extra_metadata=meta,
            speed="",
            eta="",
        )
        logger.info("Download completed for job %s → %s", job_id, output_path)

    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        if "cancelled" in msg.lower():
            _save_job_fields(
                job_id,
                status=JobStatus.CANCELLED,
                completed_at=timezone.now(),
                stage="Cancelled",
                error_message="Download cancelled by user.",
            )
            logger.info("Download cancelled: job %s", job_id)
        else:
            _save_job_fields(
                job_id,
                status=JobStatus.FAILED,
                completed_at=timezone.now(),
                stage="Failed",
                error_message=_clean_error(msg),
            )
            logger.error("Download failed for job %s: %s", job_id, msg)

    except Exception as exc:
        _save_job_fields(
            job_id,
            status=JobStatus.FAILED,
            completed_at=timezone.now(),
            stage="Failed",
            error_message=_clean_error(str(exc)),
        )
        logger.exception("Unexpected error for download job %s", job_id)


# ---------------------------------------------------------------------------
# Playlist download
# ---------------------------------------------------------------------------

def run_playlist_job(job_id: str, cancel_check: Callable[[], bool]):
    """
    Execute a playlist download job.
    Iterates over selected PlaylistItems and downloads each in sequence.
    """
    try:
        parent_job = DownloadJob.objects.get(pk=job_id)
    except DownloadJob.DoesNotExist:
        logger.error("Playlist job %s not found", job_id)
        return

    _save_job_fields(
        job_id,
        status=JobStatus.RUNNING,
        started_at=timezone.now(),
        stage="Starting playlist",
    )

    items = list(
        PlaylistItem.objects.filter(
            playlist_job_id=job_id, selected=True
        ).order_by("index")
    )
    total = len(items)

    if total == 0:
        _save_job_fields(
            job_id,
            status=JobStatus.COMPLETED,
            completed_at=timezone.now(),
            progress_pct=100.0,
            stage="No items selected",
        )
        return

    output_dir = Path(parent_job.output_dir) if parent_job.output_dir else settings.DEFAULT_DOWNLOAD_DIR
    output_dir = output_dir / (parent_job.title or "playlist")
    output_dir.mkdir(parents=True, exist_ok=True)

    completed_count = 0
    failed_count = 0

    for idx, item in enumerate(items, start=1):
        if cancel_check():
            _save_item_fields(str(item.id), status=JobStatus.CANCELLED)
            _save_job_fields(
                job_id,
                status=JobStatus.CANCELLED,
                completed_at=timezone.now(),
                stage="Cancelled",
            )
            return

        _save_item_fields(
            str(item.id),
            status=JobStatus.RUNNING,
            progress_pct=0.0,
        )
        _save_job_fields(
            job_id,
            stage=f"Downloading {idx}/{total}: {item.title[:60]}",
            progress_pct=round((idx - 1) / total * 100, 1),
        )

        try:
            opts = _build_ydl_opts(parent_job, output_dir, cancel_check, item_id=str(item.id))
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(item.url, download=True)

            output_path = _find_output_file(info, output_dir, opts)
            _save_item_fields(
                str(item.id),
                status=JobStatus.COMPLETED,
                progress_pct=100.0,
                output_path=str(output_path) if output_path else "",
            )
            completed_count += 1

        except Exception as exc:
            msg = str(exc)
            logger.error("Playlist item %s failed: %s", item.id, msg)
            _save_item_fields(
                str(item.id),
                status=JobStatus.FAILED,
                error_message=_clean_error(msg),
            )
            failed_count += 1
            # Continue with remaining items

    final_status = JobStatus.COMPLETED
    if failed_count == total:
        final_status = JobStatus.FAILED
    elif failed_count > 0:
        final_status = JobStatus.COMPLETED  # partial success

    _save_job_fields(
        job_id,
        status=final_status,
        completed_at=timezone.now(),
        progress_pct=100.0,
        stage=f"Done: {completed_count} succeeded, {failed_count} failed",
        speed="",
        eta="",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_ydl_opts(
    job: DownloadJob,
    output_dir: Path,
    cancel_check: Callable[[], bool],
    item_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build yt-dlp options dict from a job configuration."""
    from downloader.models import AppSettings

    app_cfg = AppSettings.get()
    template = job.filename_template or app_cfg.filename_template or "%(uploader)s - %(title)s.%(ext)s"

    hook_job_id = item_id if item_id else str(job.id)
    if item_id:
        # Use item-specific progress hook
        hook = _PlaylistItemProgressHook(item_id, cancel_check)
    else:
        hook = _ProgressHook(str(job.id), cancel_check)

    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "outtmpl": str(output_dir / template),
        "ffmpeg_location": app_cfg.resolved_ffmpeg_path,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "continuedl": True,
        "ignoreerrors": False,
    }

    if job.audio_only:
        fmt = (job.output_format or "original").lower()
        quality = (job.output_quality or "original").lower()

        # Resolve legacy quality presets safely
        if quality in ("best", "high", "medium", "low"):
            legacy_map = getattr(settings, "LEGACY_QUALITY_MAP", {})
            quality = legacy_map.get(quality, "mp3_256")

        opts["format"] = "bestaudio/best"

        if fmt == "original" or quality == "original":
            # Mode A: Original / Best Available
            # Preserve original audio stream and container without lossy re-encoding
            opts["postprocessors"] = [
                {"key": "FFmpegMetadata"},
            ]
        elif quality == "mp3_vbr_high":
            # Mode E: MP3 VBR High Quality (-q:a 2)
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": None,
                },
                {"key": "FFmpegMetadata"},
            ]
            opts["postprocessor_args"] = {"ExtractAudio": ["-q:a", "2"]}
        else:
            # Mode B, C, D: Fixed bitrate CBR MP3 or other explicit audio formats
            target_codec = "mp3" if fmt in ("mp3", "original") else fmt
            quality_presets = settings.AUDIO_QUALITY_PRESETS.get(target_codec, {})
            preset = quality_presets.get(quality, {})
            bitrate = preset.get("bitrate") if preset else None

            if not bitrate:
                if quality == "mp3_320":
                    bitrate = "320k"
                elif quality == "mp3_256":
                    bitrate = "256k"
                elif quality == "mp3_192":
                    bitrate = "192k"
                else:
                    bitrate = "256k"

            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": target_codec,
                    "preferredquality": bitrate.rstrip("k") if bitrate else "256",
                },
                {"key": "FFmpegMetadata"},
            ]
    else:
        opts["format"] = "bestvideo+bestaudio/best"
        opts["merge_output_format"] = "mp4"

    return opts


class _PlaylistItemProgressHook:
    def __init__(self, item_id: str, cancel_check: Callable[[], bool]):
        self.item_id = item_id
        self.cancel_check = cancel_check
        self._last_pct = 0.0

    def __call__(self, d: Dict[str, Any]):
        if self.cancel_check():
            raise yt_dlp.utils.DownloadError("Job cancelled by user")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            pct = (downloaded / total * 100.0) if total else 0.0
            if abs(pct - self._last_pct) >= 2.0:
                self._last_pct = pct
                _save_item_fields(self.item_id, progress_pct=round(pct, 1))


def _find_output_file(
    info: Optional[Dict], output_dir: Path, opts: Dict
) -> Optional[Path]:
    """Try to locate the output file after download."""
    if not info:
        return None

    # yt-dlp records the filename in info["requested_downloads"]
    downloads = info.get("requested_downloads") or []
    for dl in downloads:
        fp = dl.get("filepath") or dl.get("filename")
        if fp:
            p = Path(fp)
            if p.exists():
                return p

    # Fall back: look for a file matching the title
    title = (info.get("title") or "")[:50]
    if title:
        for f in output_dir.iterdir():
            if title[:20].lower() in f.name.lower():
                return f

    return None


def _clean_error(msg: str) -> str:
    """Strip yt-dlp verbose prefix from error messages."""
    return re.sub(r"^ERROR:\s*", "", msg, flags=re.IGNORECASE).strip()[:1000]
