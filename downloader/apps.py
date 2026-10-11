"""Django AppConfig for the downloader application."""

from django.apps import AppConfig


class DownloaderConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "downloader"
    verbose_name = "Media Downloader"

    def ready(self):
        """Start the background job manager when Django starts."""
        # Only start in the main process (avoid double-start with reloader)
        import os

        if os.environ.get("RUN_MAIN") != "true" and not os.environ.get(
            "DJANGO_COLLECTSTATIC"
        ):
            return

        from downloader.workers.job_manager import get_job_manager

        manager = get_job_manager()
        manager.start()
