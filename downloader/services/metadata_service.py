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
    from downloader.utils.validators import is_playlist_url
    if is_playlist_url(url):
        pl_info = fetch_playlist_info(url)
        return {
            "title": pl_info.get("title", "Playlist"),
            "uploader": pl_info.get("uploader", ""),
            "duration": None,
            "thumbnail": pl_info.get("thumbnail", ""),
            "description": f"Playlist containing {pl_info.get('entry_count', 0)} tracks.",
            "webpage_url": pl_info.get("webpage_url", url),
            "extractor": "youtube:playlist",
            "is_live": False,
            "upload_date": "",
            "formats": [],
            "id": pl_info.get("title", ""),
            "is_playlist": True,
            "entry_count": pl_info.get("entry_count", 0),
            "entries": pl_info.get("entries", []),
        }

    opts = _ydl_opts_base()
    opts["noplaylist"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        if "playlist" in msg.lower() or "list=" in url.lower():
            pl_info = fetch_playlist_info(url)
            return {
                "title": pl_info.get("title", "Playlist"),
                "uploader": pl_info.get("uploader", ""),
                "duration": None,
                "thumbnail": pl_info.get("thumbnail", ""),
                "description": f"Playlist containing {pl_info.get('entry_count', 0)} tracks.",
                "webpage_url": pl_info.get("webpage_url", url),
                "extractor": "youtube:playlist",
                "is_live": False,
                "upload_date": "",
                "formats": [],
                "id": pl_info.get("title", ""),
                "is_playlist": True,
                "entry_count": pl_info.get("entry_count", 0),
                "entries": pl_info.get("entries", []),
            }
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        raise RuntimeError(f"Metadata extraction failed: {exc}") from exc

    if not info:
        raise RuntimeError("No media information returned for this URL.")

    if info.get("_type") == "playlist":
        pl_info = fetch_playlist_info(url)
        return {
            "title": pl_info.get("title", "Playlist"),
            "uploader": pl_info.get("uploader", ""),
            "duration": None,
            "thumbnail": pl_info.get("thumbnail", ""),
            "description": f"Playlist containing {pl_info.get('entry_count', 0)} tracks.",
            "webpage_url": pl_info.get("webpage_url", url),
            "extractor": "youtube:playlist",
            "is_live": False,
            "upload_date": "",
            "formats": [],
            "id": pl_info.get("title", ""),
            "is_playlist": True,
            "entry_count": pl_info.get("entry_count", 0),
            "entries": pl_info.get("entries", []),
        }

    return _normalise_info(info)


def fetch_playlist_info(url: str) -> Dict[str, Any]:
    """
    Extract playlist metadata including entry listing.

    Returns a dict with:
        title, uploader, entries (list of track dicts), webpage_url
    Raises RuntimeError on failure.
    """
    normalised_url = url.replace("music.youtube.com", "www.youtube.com")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": False,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(normalised_url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        raise RuntimeError(f"Playlist metadata extraction failed: {exc}") from exc

    if not info:
        raise RuntimeError("No playlist information returned for this URL.")

    # Top-level thumbnail fallback
    thumb = info.get("thumbnail") or ""
    if not thumb and info.get("thumbnails"):
        try:
            thumb = info["thumbnails"][-1].get("url", "")
        except Exception:
            pass

    entries = []
    for idx, entry in enumerate(info.get("entries") or [], start=1):
        if entry is None or not isinstance(entry, dict):
            continue
        track_url = entry.get("url") or entry.get("webpage_url", "")
        track_id = entry.get("id", "")
        if track_url and not str(track_url).startswith("http"):
            if str(track_url).startswith("/"):
                track_url = f"https://www.youtube.com{track_url}"
            else:
                track_url = f"https://www.youtube.com/watch?v={track_url}"
        elif not track_url and track_id:
            track_url = f"https://www.youtube.com/watch?v={track_id}"

        track_thumb = entry.get("thumbnail") or ""
        if not track_thumb and entry.get("thumbnails"):
            try:
                track_thumb = entry["thumbnails"][-1].get("url", "")
            except Exception:
                pass

        entries.append(
            {
                "index": idx,
                "url": track_url,
                "title": entry.get("title", f"Track {idx}"),
                "uploader": entry.get("uploader", ""),
                "duration": entry.get("duration"),
                "thumbnail": track_thumb or thumb,
                "id": track_id,
            }
        )

    if not entries and info.get("id"):
        track_url = info.get("webpage_url") or info.get("url") or normalised_url
        entries.append(
            {
                "index": 1,
                "url": track_url,
                "title": info.get("title", "Track 1"),
                "uploader": info.get("uploader", ""),
                "duration": info.get("duration"),
                "thumbnail": thumb,
                "id": info.get("id", ""),
            }
        )

    if not thumb and entries:
        thumb = entries[0].get("thumbnail", "")

    return {
        "title": info.get("title", "Unknown Playlist"),
        "uploader": info.get("uploader", ""),
        "webpage_url": info.get("webpage_url", url),
        "thumbnail": thumb,
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
