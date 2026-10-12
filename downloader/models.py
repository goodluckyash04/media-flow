"""
Database models for the media downloader application.

Models:
  - AppSettings  : Single-row application configuration
  - DownloadJob  : Tracks download jobs (single media or playlist)
  - ConversionJob: Tracks local file conversion jobs
  - PlaylistItem : Individual items within a playlist job
"""

import uuid
from pathlib import Path

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class JobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class JobType(models.TextChoices):
    DOWNLOAD = "download", "Download"
    CONVERSION = "conversion", "Conversion"
    PLAYLIST = "playlist", "Playlist"


class AudioFormat(models.TextChoices):
    ORIGINAL = "original", "Original / Best Available"
    MP3 = "mp3", "MP3"
    M4A = "m4a", "M4A / AAC"
    FLAC = "flac", "FLAC"
    WAV = "wav", "WAV"
    OPUS = "opus", "Opus"


# ---------------------------------------------------------------------------
# AppSettings
# ---------------------------------------------------------------------------

class AppSettings(models.Model):
    """
    Single-row configuration model. Use AppSettings.get() to retrieve it.
    """

    # Download
    download_dir = models.TextField(default="")
    filename_template = models.CharField(
        max_length=500, default="%(uploader)s - %(title)s.%(ext)s"
    )
    max_concurrent_jobs = models.PositiveSmallIntegerField(default=3)

    # Audio defaults
    default_audio_format = models.CharField(
        max_length=10, choices=AudioFormat.choices, default=AudioFormat.ORIGINAL
    )
    default_audio_quality = models.CharField(max_length=20, default="original")

    # Theme
    theme = models.CharField(
        max_length=10,
        choices=[("dark", "Dark"), ("light", "Light")],
        default="dark",
    )

    # External tools
    ffmpeg_path = models.CharField(max_length=500, default="ffmpeg")
    ffprobe_path = models.CharField(max_length=500, default="ffprobe")

    # Spotify
    spotify_client_id = models.CharField(max_length=100, blank=True, default="")
    spotify_client_secret = models.CharField(max_length=100, blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Application Settings"
        verbose_name_plural = "Application Settings"

    def __str__(self):
        return "Application Settings"

    @classmethod
    def get(cls):
        """Return the singleton settings row, creating it if needed."""
        from django.conf import settings as django_settings

        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                "download_dir": str(django_settings.DEFAULT_DOWNLOAD_DIR),
                "max_concurrent_jobs": django_settings.MAX_CONCURRENT_JOBS,
                "default_audio_format": django_settings.DEFAULT_AUDIO_FORMAT,
                "default_audio_quality": django_settings.DEFAULT_AUDIO_QUALITY,
                "ffmpeg_path": django_settings.FFMPEG_PATH,
                "ffprobe_path": django_settings.FFPROBE_PATH,
                "spotify_client_id": django_settings.SPOTIFY_CLIENT_ID,
                "spotify_client_secret": django_settings.SPOTIFY_CLIENT_SECRET,
                "theme": django_settings.DEFAULT_THEME,
            },
        )
        update_fields = []
        if not created and (obj.ffmpeg_path == "ffmpeg" or not obj.ffmpeg_path):
            if django_settings.FFMPEG_PATH != "ffmpeg":
                obj.ffmpeg_path = django_settings.FFMPEG_PATH
                obj.ffprobe_path = django_settings.FFPROBE_PATH
                update_fields.extend(["ffmpeg_path", "ffprobe_path"])

        # Normalize any legacy quality preset stored in DB
        legacy_quality_map = {
            "high": "mp3_320",
            "best": "original",
            "medium": "mp3_256",
            "low": "mp3_192",
        }
        valid_qualities = {"original", "mp3_320", "mp3_256", "mp3_192", "mp3_vbr_high"}
        if obj.default_audio_quality not in valid_qualities:
            obj.default_audio_quality = legacy_quality_map.get(obj.default_audio_quality, "original")
            update_fields.append("default_audio_quality")

        if update_fields:
            obj.save(update_fields=list(set(update_fields)))
        return obj

    @property
    def resolved_ffmpeg_path(self) -> str:
        from django.conf import settings as django_settings
        if self.ffmpeg_path and Path(self.ffmpeg_path).exists():
            return self.ffmpeg_path
        if django_settings.FFMPEG_PATH and Path(django_settings.FFMPEG_PATH).exists():
            return django_settings.FFMPEG_PATH
        return self.ffmpeg_path or django_settings.FFMPEG_PATH

    @property
    def resolved_ffprobe_path(self) -> str:
        from django.conf import settings as django_settings
        if self.ffprobe_path and Path(self.ffprobe_path).exists():
            return self.ffprobe_path
        if django_settings.FFPROBE_PATH and Path(django_settings.FFPROBE_PATH).exists():
            return django_settings.FFPROBE_PATH
        return self.ffprobe_path or django_settings.FFPROBE_PATH

    @property
    def download_dir_path(self) -> Path:
        from django.conf import settings as django_settings

        p = Path(self.download_dir) if self.download_dir else django_settings.DEFAULT_DOWNLOAD_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def resolved_audio_quality(self) -> str:
        qual = (self.default_audio_quality or "").lower()
        if qual in ("best", "high", "medium", "low"):
            from django.conf import settings as django_settings
            return getattr(django_settings, "LEGACY_QUALITY_MAP", {}).get(qual, "mp3_256")
        return qual or "original"


# ---------------------------------------------------------------------------
# DownloadJob
# ---------------------------------------------------------------------------

class DownloadJob(models.Model):
    """Represents a single media or playlist download job."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(
        max_length=20, choices=JobType.choices, default=JobType.DOWNLOAD
    )
    status = models.CharField(
        max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED
    )

    # Source information
    url = models.URLField(max_length=2000)
    title = models.CharField(max_length=500, blank=True, default="")
    uploader = models.CharField(max_length=200, blank=True, default="")
    duration = models.PositiveIntegerField(null=True, blank=True)  # seconds
    thumbnail_url = models.URLField(max_length=2000, blank=True, default="")
    description = models.TextField(blank=True, default="")
    source_format = models.CharField(max_length=50, blank=True, default="")
    source_quality = models.CharField(max_length=50, blank=True, default="")

    # Download options
    audio_only = models.BooleanField(default=True)
    output_format = models.CharField(
        max_length=10, choices=AudioFormat.choices, default=AudioFormat.MP3
    )
    output_quality = models.CharField(max_length=20, default="mp3_256")
    output_dir = models.TextField(default="")
    filename_template = models.CharField(max_length=500, blank=True, default="")

    # Output
    output_path = models.TextField(blank=True, default="")
    file_size = models.BigIntegerField(null=True, blank=True)  # bytes

    # Progress
    progress_pct = models.FloatField(default=0.0)
    speed = models.CharField(max_length=50, blank=True, default="")  # e.g. "1.2 MiB/s"
    eta = models.CharField(max_length=50, blank=True, default="")  # e.g. "00:42"
    stage = models.CharField(max_length=200, blank=True, default="")

    # Error
    error_message = models.TextField(blank=True, default="")

    # Timing
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Extra metadata stored as JSON text
    extra_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Download Job"
        verbose_name_plural = "Download Jobs"

    def __str__(self):
        return f"[{self.status}] {self.title or self.url}"

    @property
    def duration_display(self) -> str:
        if not self.duration:
            return ""
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def file_size_display(self) -> str:
        from downloader.utils.file_utils import human_readable_size
        return human_readable_size(self.file_size)

    @property
    def is_active(self) -> bool:
        return self.status in (JobStatus.QUEUED, JobStatus.RUNNING)

    @property
    def output_filename(self) -> str:
        if self.output_path:
            return Path(self.output_path).name
        return ""

    @property
    def output_info(self) -> dict:
        return (self.extra_metadata or {}).get("output_info", {})

    @property
    def actual_codec(self) -> str:
        return self.output_info.get("audio_codec") or ""

    @property
    def actual_container(self) -> str:
        fmt = self.output_info.get("format_name") or ""
        if fmt:
            return fmt.split(",")[0].strip()
        if self.output_path:
            return Path(self.output_path).suffix.lstrip(".")
        return self.output_format

    @property
    def actual_bitrate(self):
        br = self.output_info.get("audio_bitrate")
        try:
            return int(br) if br else None
        except (ValueError, TypeError):
            return None

    @property
    def actual_bitrate_display(self) -> str:
        br = self.actual_bitrate
        if br and br > 0:
            return f"{round(br / 1000)} kbps"
        return "Unknown"

    @property
    def source_bitrate_display(self) -> str:
        br = (self.extra_metadata or {}).get("source_bitrate")
        if br:
            try:
                val = int(br)
                if val > 1000:
                    val = round(val / 1000)
                return f"{val} kbps"
            except (ValueError, TypeError):
                pass
        return "Unknown"

    @property
    def target_bitrate_display(self) -> str:
        qual = (self.output_quality or "").lower()
        if qual == "original" or self.output_format == "original":
            return "N/A (Source preserved)"
        if qual in ("mp3_320", "best"):
            return "320 kbps (CBR)"
        if qual in ("mp3_256", "high"):
            return "256 kbps (CBR)"
        if qual in ("mp3_192", "medium"):
            return "192 kbps (CBR)"
        if qual == "mp3_vbr_high":
            return "VBR (~190–250 kbps)"
        return "Unknown"

    @property
    def actual_sample_rate(self):
        sr = self.output_info.get("sample_rate")
        return f"{sr} Hz" if sr else ""

    @property
    def audio_summary_display(self) -> str:
        parts = []
        if self.actual_codec:
            parts.append(self.actual_codec.upper())
        if self.actual_container:
            parts.append(self.actual_container.upper())
        if self.actual_bitrate_display != "Unknown":
            parts.append(self.actual_bitrate_display)
        if self.actual_sample_rate:
            parts.append(self.actual_sample_rate)
        return " · ".join(parts) if parts else (self.output_format.upper())


# ---------------------------------------------------------------------------
# PlaylistItem
# ---------------------------------------------------------------------------

class PlaylistItem(models.Model):
    """Individual track in a playlist download job."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playlist_job = models.ForeignKey(
        DownloadJob, on_delete=models.CASCADE, related_name="playlist_items"
    )

    index = models.PositiveIntegerField(default=0)
    url = models.URLField(max_length=2000)
    title = models.CharField(max_length=500, blank=True, default="")
    uploader = models.CharField(max_length=200, blank=True, default="")
    duration = models.PositiveIntegerField(null=True, blank=True)
    thumbnail_url = models.URLField(max_length=2000, blank=True, default="")

    status = models.CharField(
        max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED
    )
    selected = models.BooleanField(default=True)
    output_path = models.TextField(blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    progress_pct = models.FloatField(default=0.0)

    class Meta:
        ordering = ["index"]
        verbose_name = "Playlist Item"

    def __str__(self):
        return f"#{self.index}: {self.title or self.url}"

    @property
    def duration_display(self) -> str:
        if not self.duration:
            return ""
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# ConversionJob
# ---------------------------------------------------------------------------

class ConversionJob(models.Model):
    """Tracks a local file audio conversion job."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(
        max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED
    )

    # Source
    input_path = models.TextField()
    input_filename = models.CharField(max_length=500, blank=True, default="")
    input_size = models.BigIntegerField(null=True, blank=True)
    input_duration = models.FloatField(null=True, blank=True)  # seconds

    # Output options
    output_format = models.CharField(
        max_length=10, choices=AudioFormat.choices, default=AudioFormat.MP3
    )
    output_quality = models.CharField(max_length=20, default="mp3_256")
    output_dir = models.TextField(default="")
    output_path = models.TextField(blank=True, default="")
    output_size = models.BigIntegerField(null=True, blank=True)

    # Progress
    progress_pct = models.FloatField(default=0.0)
    stage = models.CharField(max_length=200, blank=True, default="")

    # Error
    error_message = models.TextField(blank=True, default="")

    # Timing
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Conversion Job"
        verbose_name_plural = "Conversion Jobs"

    def __str__(self):
        return f"[{self.status}] {self.input_filename} → {self.output_format}"

    @property
    def is_active(self) -> bool:
        return self.status in (JobStatus.QUEUED, JobStatus.RUNNING)

    @property
    def output_filename(self) -> str:
        if self.output_path:
            return Path(self.output_path).name
        return ""
