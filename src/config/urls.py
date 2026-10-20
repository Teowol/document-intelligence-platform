from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import include, path
from django.views.i18n import set_language

from config.health import healthz


def home(request):
    """Introduce the platform to visitors; return members to their workspace."""
    if request.user.is_authenticated:
        return redirect("documents:dashboard")
    return render(request, "home.html", {"is_landing": True})


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
