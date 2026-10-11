"""Django admin configuration for the downloader app."""

from django.contrib import admin

from downloader.models import AppSettings, ConversionJob, DownloadJob, PlaylistItem


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    list_display = ["pk", "default_audio_format", "max_concurrent_jobs", "updated_at"]


@admin.register(DownloadJob)
class DownloadJobAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "job_type", "output_format", "progress_pct", "created_at"]
    list_filter = ["status", "job_type", "output_format"]
    search_fields = ["title", "url", "uploader"]
    readonly_fields = ["id", "created_at", "started_at", "completed_at"]
    ordering = ["-created_at"]


@admin.register(PlaylistItem)
class PlaylistItemAdmin(admin.ModelAdmin):
    list_display = ["title", "index", "status", "selected", "playlist_job"]
    list_filter = ["status", "selected"]
    search_fields = ["title", "url"]


@admin.register(ConversionJob)
class ConversionJobAdmin(admin.ModelAdmin):
    list_display = ["input_filename", "output_format", "status", "progress_pct", "created_at"]
    list_filter = ["status", "output_format"]
    search_fields = ["input_filename", "input_path"]
    readonly_fields = ["id", "created_at", "started_at", "completed_at"]
