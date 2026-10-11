"""URL patterns for the downloader application."""

from django.urls import path

from downloader import views

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # Download
    path("download/", views.download_new, name="download"),
    path("download/inspect/", views.inspect_url, name="inspect_url"),

    # Playlist
    path("playlist/", views.playlist_view, name="playlist"),

    # Converter
    path("converter/", views.converter_view, name="converter"),

    # Queue
    path("queue/", views.queue_view, name="queue"),
    path("queue/status/", views.queue_status, name="queue_status"),

    # Progress API
    path("api/progress/download/<str:job_id>/", views.job_progress, name="job_progress"),
    path("api/progress/conversion/<str:job_id>/", views.conversion_progress, name="conversion_progress"),

    # Cancel / retry actions
    path("api/cancel/download/<str:job_id>/", views.cancel_download, name="cancel_download"),
    path("api/retry/download/<str:job_id>/", views.retry_download, name="retry_download"),
    path("api/cancel/conversion/<str:job_id>/", views.cancel_conversion, name="cancel_conversion"),
    path("api/retry/conversion/<str:job_id>/", views.retry_conversion, name="retry_conversion"),

    # Library / History
    path("library/", views.library_view, name="library"),
    path("api/delete/<str:job_id>/", views.delete_history_record, name="delete_record"),
    path("api/open-folder/<str:job_id>/", views.open_output_folder, name="open_folder"),

    # Settings
    path("settings/", views.settings_view, name="settings"),
    path("api/update-ytdlp/", views.update_ytdlp, name="update_ytdlp"),

    # Spotify
    path("api/spotify/inspect/", views.spotify_inspect, name="spotify_inspect"),
]
