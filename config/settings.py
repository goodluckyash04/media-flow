"""
Django settings for the Local Media Downloader & Audio Converter.

This application is designed for local, single-user personal use only.
The development server is NOT intended for production or network exposure.
"""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    secrets.token_urlsafe(50),  # generated at startup if not set
)

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

_raw_hosts = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8001",
    "http://localhost:8001",
]

FORMS_URLFIELD_ASSUME_HTTPS = True

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "downloader",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "downloader.context_processors.app_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
            "check_same_thread": False,
        },
    }
}

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Default auto field
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGS_DIR = BASE_DIR / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "app.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "downloader": {
            "handlers": ["console", "file"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Application-specific settings
# ---------------------------------------------------------------------------

# Download directory
_default_download = Path.home() / "Downloads" / "MediaDownloader"
DEFAULT_DOWNLOAD_DIR = Path(
    os.getenv("DEFAULT_DOWNLOAD_DIR", "") or _default_download
)

# FFmpeg / FFprobe (defaults to project-local bin/ if present)
_local_ffmpeg = BASE_DIR / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
_local_ffprobe = BASE_DIR / "bin" / ("ffprobe.exe" if os.name == "nt" else "ffprobe")

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "") or (str(_local_ffmpeg) if _local_ffmpeg.exists() else "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "") or (str(_local_ffprobe) if _local_ffprobe.exists() else "ffprobe")

# Job concurrency
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "3"))

# Audio defaults
DEFAULT_AUDIO_FORMAT = os.getenv("DEFAULT_AUDIO_FORMAT", "mp3")
DEFAULT_AUDIO_QUALITY = os.getenv("DEFAULT_AUDIO_QUALITY", "high")

# Filename template (yt-dlp style)
FILENAME_TEMPLATE = os.getenv(
    "FILENAME_TEMPLATE", "%(uploader)s - %(title)s.%(ext)s"
)

# Theme
DEFAULT_THEME = os.getenv("DEFAULT_THEME", "dark")

# Spotify (optional)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# Server port
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# Job polling interval (milliseconds, used by frontend)
JOB_POLL_INTERVAL_MS = 2000

# Supported audio formats and their display labels
SUPPORTED_AUDIO_FORMATS = {
    "mp3": "MP3",
    "m4a": "M4A / AAC",
    "flac": "FLAC (Lossless)",
    "wav": "WAV (Uncompressed)",
    "opus": "Opus",
}

# Quality presets per format
AUDIO_QUALITY_PRESETS = {
    "mp3": {
        "best": {"bitrate": "320k", "label": "Best (320 kbps)"},
        "high": {"bitrate": "256k", "label": "High (256 kbps)"},
        "medium": {"bitrate": "192k", "label": "Medium (192 kbps)"},
        "low": {"bitrate": "128k", "label": "Low (128 kbps)"},
    },
    "m4a": {
        "best": {"bitrate": "256k", "label": "Best (256 kbps)"},
        "high": {"bitrate": "192k", "label": "High (192 kbps)"},
        "medium": {"bitrate": "128k", "label": "Medium (128 kbps)"},
        "low": {"bitrate": "96k", "label": "Low (96 kbps)"},
    },
    "flac": {
        "best": {"bitrate": None, "label": "Lossless (no re-encoding loss)"},
    },
    "wav": {
        "best": {"bitrate": None, "label": "Uncompressed PCM"},
    },
    "opus": {
        "best": {"bitrate": "320k", "label": "Best (320 kbps)"},
        "high": {"bitrate": "192k", "label": "High (192 kbps)"},
        "medium": {"bitrate": "128k", "label": "Medium (128 kbps)"},
        "low": {"bitrate": "64k", "label": "Low (64 kbps)"},
    },
}
