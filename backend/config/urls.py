from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.common.urls")),
    path("api/v1/auth/", include("apps.accounts.api_urls")),
    path("api/v1/", include("apps.repositories.api_urls")),
    path("api/v1/", include("apps.agent.api_urls")),
    path("api/v1/", include("apps.watchlists.api_urls")),
    path("api/v1/", include("apps.interactions.api_urls")),
]
