from django.urls import path, include, re_path
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from .views import FrontendProxyView

# Serve media files first
urlpatterns = static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Then add other URL patterns
urlpatterns += [
    path('api/', include('invoices.urls')),
    path('admin/', admin.site.urls),
    # Catch-all route for frontend requests
    # Exclude any path that starts with "admin" or "api" (with or without trailing slash)
    re_path(r'^(?!(?:admin($|/)|api($|/)))(?P<path>.*)$', FrontendProxyView.as_view(), name='frontend_fallback'),
]
