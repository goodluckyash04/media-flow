"""
Input validators for URLs, paths, and audio format/quality combinations.
"""

import ipaddress
import re
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.core.exceptions import ValidationError


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

# Schemes we accept
_ALLOWED_SCHEMES = {"http", "https"}

# Private / loopback ranges to block (prevents SSRF)
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_ip(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        # Not a raw IP – skip network check (hostname resolution is deferred)
        return False


def validate_url(url: str) -> str:
    """
    Validate and normalise a media URL.
    - Rejects invalid schemes, localhost, and private IPs.
    - Validates YouTube and YouTube Music video/playlist query parameters.
    - Normalises music.youtube.com to www.youtube.com for seamless yt-dlp extraction.
    Raises ValidationError on failure.
    Returns the cleaned URL string.
    """
    url = url.strip()
    if not url:
        raise ValidationError("URL is required.")

    parsed = urlparse(url)

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValidationError(
            f"Unsupported URL scheme '{parsed.scheme}'. "
            "Only http and https are permitted."
        )

    host = parsed.hostname or ""
    if not host:
        raise ValidationError("URL must include a valid hostname.")

    if _is_private_ip(host):
        raise ValidationError(
            "URLs pointing to private or local network addresses are not permitted."
        )

    # Block localhost names
    if host.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValidationError("URLs pointing to localhost are not permitted.")

    # Validation & normalisation for YouTube / YouTube Music
    lower_host = host.lower()
    is_yt = lower_host in (
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "www.music.youtube.com",
        "youtu.be",
    )
    if is_yt:
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        if lower_host != "youtu.be":
            if path == "/watch" and "v" not in query:
                raise ValidationError(
                    "YouTube and YouTube Music track URLs must include the video ID (e.g. https://music.youtube.com/watch?v=...)."
                )
            if path == "/playlist" and "list" not in query:
                raise ValidationError(
                    "Playlist URLs must include the playlist ID (e.g. ?list=...)."
                )

        # Strip tracking parameters: 'si', 'feature', 'pp'
        if parsed.query:
            pairs = parse_qsl(parsed.query, keep_blank_values=True)
            filtered = [(k, v) for k, v in pairs if k.lower() not in ("si", "feature", "pp")]
            parsed = parsed._replace(query=urlencode(filtered))

        # Normalise music.youtube.com to www.youtube.com for 100% extraction compatibility
        if lower_host in ("music.youtube.com", "www.music.youtube.com"):
            parsed = parsed._replace(netloc="www.youtube.com")

        return urlunparse(parsed)

    return url


def validate_output_dir(path_str: str) -> Path:
    """
    Validate that a given path string is acceptable as an output directory.
    Returns a resolved Path object.
    Raises ValidationError if the path is not acceptable.
    """
    if not path_str or not path_str.strip():
        raise ValidationError("Output directory is required.")

    p = Path(path_str.strip())

    try:
        resolved = p.resolve()
    except Exception as exc:
        raise ValidationError(f"Invalid path: {exc}") from exc

    # Prevent writing to system directories
    dangerous_prefixes = [
        Path("C:/Windows"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("/etc"),
        Path("/bin"),
        Path("/usr"),
    ]
    for prefix in dangerous_prefixes:
        try:
            if resolved.is_relative_to(prefix.resolve()):
                raise ValidationError(
                    f"Output directory cannot be inside a system directory: {prefix}"
                )
        except ValueError:
            pass

    return resolved


def validate_audio_format(fmt: str) -> str:
    allowed = set(settings.SUPPORTED_AUDIO_FORMATS.keys())
    if fmt not in allowed:
        raise ValidationError(
            f"Unsupported audio format '{fmt}'. "
            f"Choose from: {', '.join(sorted(allowed))}."
        )
    return fmt


def validate_audio_quality(quality: str, fmt: str) -> str:
    presets = settings.AUDIO_QUALITY_PRESETS.get(fmt, {})
    if not presets:
        return quality  # no restriction for unknown format
    if quality not in presets:
        raise ValidationError(
            f"Quality '{quality}' is not available for format '{fmt}'. "
            f"Choose from: {', '.join(presets.keys())}."
        )
    return quality


# ---------------------------------------------------------------------------
# Filename template validation
# ---------------------------------------------------------------------------

_VALID_TEMPLATE_VARS = {
    "%(title)s", "%(uploader)s", "%(id)s", "%(ext)s",
    "%(upload_date)s", "%(duration)s", "%(playlist_index)s",
    "%(playlist)s", "%(autonumber)s",
}

_TEMPLATE_VAR_RE = re.compile(r"%\([^)]+\)s")


def validate_filename_template(template: str) -> str:
    """Basic sanity check on a yt-dlp filename template."""
    if not template.strip():
        raise ValidationError("Filename template cannot be empty.")
    # Must contain at least one yt-dlp placeholder
    if not _TEMPLATE_VAR_RE.search(template):
        raise ValidationError(
            "Filename template must contain at least one yt-dlp variable "
            "such as %(title)s or %(id)s."
        )
    # Check for dangerous characters outside of template vars
    cleaned = _TEMPLATE_VAR_RE.sub("", template)
    dangerous = set('<>:"|?*\x00')
    bad_chars = dangerous.intersection(set(cleaned))
    if bad_chars:
        raise ValidationError(
            f"Filename template contains forbidden characters: "
            f"{', '.join(repr(c) for c in bad_chars)}"
        )
    return template.strip()
