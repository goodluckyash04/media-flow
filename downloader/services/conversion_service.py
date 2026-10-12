"""
Conversion service: runs FFmpeg to extract or transcode audio
from local video/audio files.

All FFmpeg commands use subprocess with explicit argument lists
(no shell string interpolation) for safety.
"""

import logging
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone

from downloader.models import AppSettings, ConversionJob, JobStatus
from downloader.utils.file_utils import safe_output_path

logger = logging.getLogger(__name__)

_db_lock = threading.Lock()


def _save_job(job_id: str, **kwargs):
    with _db_lock:
        ConversionJob.objects.filter(pk=job_id).update(**kwargs)


# ---------------------------------------------------------------------------
# FFmpeg detection
# ---------------------------------------------------------------------------

def detect_ffmpeg(ffmpeg_path: str = "ffmpeg") -> Tuple[bool, str]:
    """
    Return (available: bool, version_string: str).
    Uses the configured path from AppSettings.
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            first_line = result.stdout.splitlines()[0] if result.stdout else ""
            return True, first_line
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False, ""


def detect_ffprobe(ffprobe_path: str = "ffprobe") -> Tuple[bool, str]:
    """Return (available: bool, version_string: str) for ffprobe."""
    try:
        result = subprocess.run(
            [ffprobe_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            first_line = result.stdout.splitlines()[0] if result.stdout else ""
            return True, first_line
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False, ""


# ---------------------------------------------------------------------------
# Media info via ffprobe
# ---------------------------------------------------------------------------

def probe_file(file_path: Path) -> Dict:
    """
    Return basic metadata for a local file via ffprobe.
    Returns a dict with: duration, audio_codec, video_codec, format_name, size.
    """
    app_cfg = AppSettings.get()
    ffprobe = app_cfg.resolved_ffprobe_path

    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(file_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe error: {result.stderr[:200]}")

        import json
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})

        dur = float(fmt.get("duration", 0))
        size_bytes = int(fmt.get("size", 0)) or (file_path.stat().st_size if file_path.exists() else 0)
        bitrate = audio_stream.get("bit_rate") or fmt.get("bit_rate")
        if not bitrate and dur > 0 and size_bytes > 0:
            bitrate = int((size_bytes * 8) / dur)

        return {
            "duration": dur,
            "size": size_bytes,
            "format_name": fmt.get("format_name", ""),
            "audio_codec": audio_stream.get("codec_name", ""),
            "audio_bitrate": int(bitrate) if bitrate else None,
            "sample_rate": int(audio_stream.get("sample_rate")) if audio_stream.get("sample_rate") else None,
            "channels": int(audio_stream.get("channels")) if audio_stream.get("channels") else None,
            "channel_layout": audio_stream.get("channel_layout", ""),
            "video_codec": video_stream.get("codec_name", ""),
            "has_audio": bool(audio_stream),
            "has_video": bool(video_stream),
        }
    except Exception as exc:
        logger.warning("probe_file failed for %s: %s", file_path, exc)
        return {
            "duration": 0,
            "size": file_path.stat().st_size if file_path.exists() else 0,
            "format_name": file_path.suffix.lstrip("."),
            "audio_codec": "",
            "audio_bitrate": None,
            "sample_rate": None,
            "channels": None,
            "channel_layout": "",
            "video_codec": "",
            "has_audio": True,
            "has_video": False,
        }


# ---------------------------------------------------------------------------
# Conversion job executor
# ---------------------------------------------------------------------------

def run_conversion_job(job_id: str, cancel_check: Callable[[], bool]):
    """Execute a ConversionJob: extract/transcode audio with FFmpeg."""
    try:
        job = ConversionJob.objects.get(pk=job_id)
    except ConversionJob.DoesNotExist:
        logger.error("ConversionJob %s not found", job_id)
        return

    _save_job(
        job_id,
        status=JobStatus.RUNNING,
        started_at=timezone.now(),
        stage="Initialising",
    )

    try:
        input_path = Path(job.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_dir = Path(job.output_dir) if job.output_dir else input_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build output filename
        out_stem = input_path.stem
        out_ext = job.output_format
        output_path = safe_output_path(output_dir, f"{out_stem}.{out_ext}")

        app_cfg = AppSettings.get()
        ffmpeg = app_cfg.resolved_ffmpeg_path

        cmd = _build_ffmpeg_cmd(ffmpeg, input_path, output_path, job)
        logger.info("FFmpeg command: %s", " ".join(str(c) for c in cmd))

        _save_job(job_id, stage="Converting", output_path=str(output_path))

        # Probe for total duration to compute progress
        probe = probe_file(input_path)
        total_duration = probe.get("duration") or 0.0

        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        _monitor_ffmpeg(job_id, process, total_duration, cancel_check)

        rc = process.wait()
        if cancel_check() or rc == 255:
            output_path.unlink(missing_ok=True)
            _save_job(
                job_id,
                status=JobStatus.CANCELLED,
                completed_at=timezone.now(),
                stage="Cancelled",
            )
            logger.info("Conversion cancelled: job %s", job_id)
            return

        if rc != 0:
            raise RuntimeError(f"FFmpeg exited with code {rc}")

        if not output_path.exists():
            raise RuntimeError("FFmpeg completed but output file was not found.")

        _save_job(
            job_id,
            status=JobStatus.COMPLETED,
            completed_at=timezone.now(),
            progress_pct=100.0,
            stage="Complete",
            output_path=str(output_path),
            output_size=output_path.stat().st_size,
        )
        logger.info("Conversion complete: job %s → %s", job_id, output_path)

    except Exception as exc:
        _save_job(
            job_id,
            status=JobStatus.FAILED,
            completed_at=timezone.now(),
            stage="Failed",
            error_message=str(exc)[:1000],
        )
        logger.exception("Conversion job %s failed", job_id)


def _build_ffmpeg_cmd(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    job: ConversionJob,
) -> List[str]:
    """Build the FFmpeg argument list for an audio extraction/conversion."""
    fmt = job.output_format
    quality = job.output_quality

    quality_presets = settings.AUDIO_QUALITY_PRESETS.get(fmt, {})
    preset = quality_presets.get(quality, quality_presets.get("best", {}))
    bitrate = preset.get("bitrate") if preset else None

    cmd = [
        ffmpeg,
        "-y",                  # overwrite – safe because we control the output path
        "-i", str(input_path),
        "-vn",                 # discard video
        "-map_metadata", "0",  # preserve metadata
    ]

    if fmt == "mp3":
        cmd += ["-codec:a", "libmp3lame"]
        if quality == "mp3_vbr_high":
            cmd += ["-q:a", "2"]
        else:
            if not bitrate:
                if quality in ("mp3_320", "best"):
                    bitrate = "320k"
                elif quality in ("mp3_256", "high"):
                    bitrate = "256k"
                elif quality in ("mp3_192", "medium"):
                    bitrate = "192k"
                else:
                    bitrate = "256k"
            cmd += ["-b:a", bitrate]
    elif fmt == "original":
        cmd += ["-codec:a", "copy"]
    elif fmt == "m4a":
        cmd += ["-codec:a", "aac"]
        if bitrate:
            cmd += ["-b:a", bitrate]
    elif fmt == "flac":
        cmd += ["-codec:a", "flac"]
    elif fmt == "wav":
        cmd += ["-codec:a", "pcm_s16le"]
    elif fmt == "opus":
        cmd += ["-codec:a", "libopus"]
        if bitrate:
            cmd += ["-b:a", bitrate]
    else:
        cmd += ["-codec:a", "copy"]

    # Progress output to stderr at 1-second intervals
    cmd += ["-progress", "pipe:2", "-nostats"]
    cmd.append(str(output_path))
    return cmd


def _monitor_ffmpeg(
    job_id: str,
    process: subprocess.Popen,
    total_duration: float,
    cancel_check: Callable[[], bool],
):
    """
    Read FFmpeg's -progress output from stderr and update progress_pct.
    Terminates the process if the cancel_check returns True.
    """
    _time_re = re.compile(r"out_time_ms=(\d+)")

    for line in process.stderr:
        if cancel_check():
            process.terminate()
            return

        m = _time_re.search(line)
        if m and total_duration > 0:
            elapsed_us = int(m.group(1))
            elapsed_s = elapsed_us / 1_000_000
            pct = min(elapsed_s / total_duration * 100, 99.0)
            _save_job(job_id, progress_pct=round(pct, 1))
