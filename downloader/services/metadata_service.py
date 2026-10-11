"""
Metadata service: uses yt-dlp to extract media information
without downloading.  Returns structured dicts suitable for
template rendering and job initialisation.
"""

import logging
from typing import Any, Dict, Optional

import yt_dlp

logger = logging.getLogger(__name__)


def _ydl_opts_base(quiet: bool = True) -> Dict[str, Any]:
    return {
        "quiet": quiet,
        "no_warnings": quiet,
        "extract_flat": False,
        "skip_download": True,
        "noplaylist": True,
    }


def fetch_media_info(url: str) -> Dict[str, Any]:
    """
    Extract metadata for a single media URL using yt-dlp.

    Returns a dict with keys:
        title, uploader, duration, thumbnail, description,
        formats, webpage_url, extractor, is_live, upload_date
    Raises RuntimeError on failure.
    """
    opts = _ydl_opts_base()
    opts["noplaylist"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        raise RuntimeError(f"Metadata extraction failed: {exc}") from exc

    if not info:
        raise RuntimeError("No media information returned for this URL.")

    return _normalise_info(info)


def fetch_playlist_info(url: str) -> Dict[str, Any]:
    """
    Extract playlist metadata including entry listing.

    Returns a dict with:
        title, uploader, entries (list of track dicts), webpage_url
    Raises RuntimeError on failure.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": False,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        raise RuntimeError(f"Playlist metadata extraction failed: {exc}") from exc

    if not info:
        raise RuntimeError("No playlist information returned for this URL.")

    entries = []
    for idx, entry in enumerate(info.get("entries") or [], start=1):
        if entry is None:
            continue
        entries.append(
            {
                "index": idx,
                "url": entry.get("url") or entry.get("webpage_url", ""),
                "title": entry.get("title", f"Track {idx}"),
                "uploader": entry.get("uploader", ""),
                "duration": entry.get("duration"),
                "thumbnail": entry.get("thumbnail", ""),
                "id": entry.get("id", ""),
            }
        )

    return {
        "title": info.get("title", "Unknown Playlist"),
        "uploader": info.get("uploader", ""),
        "webpage_url": info.get("webpage_url", url),
        "thumbnail": info.get("thumbnail", ""),
        "entry_count": len(entries),
        "entries": entries,
    }


def _normalise_info(info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the fields we care about from a raw yt-dlp info dict."""
    formats = []
    for fmt in info.get("formats") or []:
        formats.append(
            {
                "format_id": fmt.get("format_id", ""),
                "ext": fmt.get("ext", ""),
                "acodec": fmt.get("acodec", "none"),
                "vcodec": fmt.get("vcodec", "none"),
                "abr": fmt.get("abr"),
                "vbr": fmt.get("vbr"),
                "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                "quality": fmt.get("quality"),
                "format_note": fmt.get("format_note", ""),
                "resolution": fmt.get("resolution", ""),
            }
        )

    return {
        "title": info.get("title", ""),
        "uploader": info.get("uploader") or info.get("channel", ""),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail", ""),
        "description": (info.get("description") or "")[:2000],
        "webpage_url": info.get("webpage_url", ""),
        "extractor": info.get("extractor", ""),
        "is_live": bool(info.get("is_live")),
        "upload_date": info.get("upload_date", ""),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "formats": formats,
        "id": info.get("id", ""),
    }
