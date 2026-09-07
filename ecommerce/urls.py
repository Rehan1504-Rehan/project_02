"""URL configuration for the ecommerce project."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("store.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    # This is useful for a small Railway deployment with a persistent Volume.
    # Larger deployments should use object storage for media instead.
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]

handler403 = "store.views.permission_denied"
handler404 = "store.views.page_not_found"
handler500 = "store.views.server_error"
