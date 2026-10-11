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
        max_length=10, choices=AudioFormat.choices, default=AudioFormat.MP3
    )
    default_audio_quality = models.CharField(max_length=20, default="high")

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
        return obj

    @property
    def download_dir_path(self) -> Path:
        from django.conf import settings as django_settings

        p = Path(self.download_dir) if self.download_dir else django_settings.DEFAULT_DOWNLOAD_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p


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
    output_quality = models.CharField(max_length=20, default="high")
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
        if not self.file_size:
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if self.file_size < 1024:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024
        return f"{self.file_size:.1f} TB"

    @property
    def is_active(self) -> bool:
        return self.status in (JobStatus.QUEUED, JobStatus.RUNNING)

    @property
    def output_filename(self) -> str:
        if self.output_path:
            return Path(self.output_path).name
        return ""


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
    output_quality = models.CharField(max_length=20, default="high")
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
