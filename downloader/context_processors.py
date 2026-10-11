"""
Template context processors for the downloader application.
These inject common variables into every template context.
"""

from django.conf import settings


def app_settings(request):
    """Inject global app settings into every template."""
    from downloader.models import AppSettings

    try:
        app_cfg = AppSettings.get()
        theme = app_cfg.theme
    except Exception:
        theme = settings.DEFAULT_THEME

    return {
        "APP_NAME": "MediaFlow",
        "APP_VERSION": "1.0.0",
        "THEME": theme,
        "POLL_INTERVAL_MS": settings.JOB_POLL_INTERVAL_MS,
        "SUPPORTED_AUDIO_FORMATS": settings.SUPPORTED_AUDIO_FORMATS,
    }
