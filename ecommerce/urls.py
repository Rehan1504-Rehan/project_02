"""URL configuration for the ecommerce project."""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from store import views as store_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("store.urls")),
]

if settings.SERVE_MEDIA:
    # Uploads are served by the same view in development and in production so
    # that a working local image cannot turn into a 404 after deployment. The
    # view reads from the database (MEDIA_STORAGE=database) and falls back to
    # MEDIA_ROOT for files written before that, or by a mounted disk.
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", store_views.serve_media, name="media"),
    ]

handler403 = "store.views.permission_denied"
handler404 = "store.views.page_not_found"
handler500 = "store.views.server_error"
