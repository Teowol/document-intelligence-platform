from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path
from django.views.i18n import set_language

from config.health import healthz


def home(request):
    """Root: authenticated users go to their dashboard, others to login."""
    if request.user.is_authenticated:
        return redirect("documents:dashboard")
    return redirect("account_login")


urlpatterns = [
    path("", home, name="home"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("set_language/", set_language, name="set_language"),
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),
    path("documents/", include("documents.urls")),
]
