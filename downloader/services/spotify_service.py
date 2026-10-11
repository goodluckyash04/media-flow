"""
Spotify service (optional integration).

This module is intentionally kept separate so the rest of the application
functions without any Spotify credentials or the spotipy library.

Usage:
  - Configure SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env.
  - The service will gracefully return an "unavailable" result when
    credentials are absent or spotipy is not installed.

IMPORTANT:
  - This service only retrieves publicly-available metadata via the
    Spotify Web API. It does NOT stream, download, or bypass DRM.
  - Track matching against downloadable sources is done by the caller.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SpotifyServiceUnavailable(Exception):
    """Raised when Spotify integration is not configured."""


def _get_client():
    """Return an authenticated spotipy client or raise SpotifyServiceUnavailable."""
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError as exc:
        raise SpotifyServiceUnavailable(
            "The 'spotipy' library is not installed. "
            "Install it with: uv pip install spotipy"
        ) from exc

    from django.conf import settings

    client_id = settings.SPOTIFY_CLIENT_ID
    client_secret = settings.SPOTIFY_CLIENT_SECRET

    if not client_id or not client_secret:
        raise SpotifyServiceUnavailable(
            "Spotify credentials are not configured. "
            "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file."
        )

    auth = SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret,
    )
    return spotipy.Spotify(auth_manager=auth)


def is_spotify_url(url: str) -> bool:
    """Return True if the URL looks like a Spotify track or playlist link."""
    return "open.spotify.com" in url or url.startswith("spotify:")


def fetch_spotify_track(url: str) -> Dict[str, Any]:
    """
    Retrieve metadata for a Spotify track.
    Returns a dict with: title, artists, album, duration_ms, release_date, external_url.
    """
    sp = _get_client()
    track_id = _extract_spotify_id(url, "track")
    if not track_id:
        raise ValueError(f"Could not extract Spotify track ID from: {url}")

    track = sp.track(track_id)
    return {
        "title": track["name"],
        "artists": [a["name"] for a in track["artists"]],
        "album": track["album"]["name"],
        "duration_ms": track["duration_ms"],
        "release_date": track["album"].get("release_date", ""),
        "external_url": track["external_urls"].get("spotify", url),
        "preview_url": track.get("preview_url"),
        "search_query": f"{track['name']} {' '.join(a['name'] for a in track['artists'])}",
    }


def fetch_spotify_playlist(url: str) -> Dict[str, Any]:
    """
    Retrieve metadata for a Spotify playlist.
    Returns a dict with: name, owner, description, tracks (list of track dicts).
    """
    sp = _get_client()
    playlist_id = _extract_spotify_id(url, "playlist")
    if not playlist_id:
        raise ValueError(f"Could not extract Spotify playlist ID from: {url}")

    playlist = sp.playlist(playlist_id)
    tracks = []

    # Paginate through all tracks
    results = playlist["tracks"]
    while results:
        for item in results["items"]:
            t = item.get("track")
            if not t:
                continue
            tracks.append(
                {
                    "title": t["name"],
                    "artists": [a["name"] for a in t.get("artists", [])],
                    "album": t.get("album", {}).get("name", ""),
                    "duration_ms": t.get("duration_ms"),
                    "search_query": f"{t['name']} {' '.join(a['name'] for a in t.get('artists', []))}",
                }
            )
        results = sp.next(results) if results.get("next") else None

    return {
        "name": playlist["name"],
        "owner": playlist["owner"]["display_name"],
        "description": playlist.get("description", ""),
        "track_count": len(tracks),
        "tracks": tracks,
    }


def build_youtube_search_url(search_query: str) -> str:
    """Build a YouTube Music search URL from a search query string."""
    import urllib.parse

    encoded = urllib.parse.quote_plus(f"{search_query} audio")
    return f"https://www.youtube.com/results?search_query={encoded}"


def _extract_spotify_id(url: str, entity_type: str) -> Optional[str]:
    """Extract a Spotify entity ID from a URL like open.spotify.com/track/<id>."""
    import re

    # Handle spotify:track:ID format
    pattern_uri = re.compile(rf"spotify:{entity_type}:([A-Za-z0-9]+)")
    m = pattern_uri.search(url)
    if m:
        return m.group(1)

    # Handle https://open.spotify.com/track/ID format
    pattern_url = re.compile(rf"open\.spotify\.com/{entity_type}/([A-Za-z0-9]+)")
    m = pattern_url.search(url)
    if m:
        return m.group(1)

    return None
