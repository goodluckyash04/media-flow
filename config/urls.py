"""URL configuration for the media downloader project."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("downloader.urls")),
]

# Custom error handlers
handler400 = "downloader.views.error_400"
handler403 = "downloader.views.error_403"
handler404 = "downloader.views.error_404"
handler500 = "downloader.views.error_500"
