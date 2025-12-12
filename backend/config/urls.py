from django.urls import path, include, re_path
from django.contrib import admin
from django.http import FileResponse, HttpResponseNotFound, HttpResponse
from django.views.static import serve
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_BUILD = BASE_DIR.parent / "webapp" / "UI for forecasting2" / "build"


def spa_index(request):
    """Serve the built React single-page app."""
    index_path = FRONTEND_BUILD / "index.html"
    if index_path.exists():
        resp = FileResponse(open(index_path, "rb"))
        # Le bundle Vite utilise des noms hashés (assets/index-XXXX.js). Pour éviter
        # de rester bloqué sur une ancienne version, on désactive le cache sur
        # l'index HTML.
        resp["Cache-Control"] = "no-store, max-age=0"
        resp["Pragma"] = "no-cache"
        resp["Expires"] = "0"
        return resp
    return HttpResponseNotFound("Front-end build not found. Run npm run build in webapp/UI for forecasting2.")


urlpatterns = [
    # Frontend SPA entrypoint
    path("", spa_index, name="spa_index"),
    # Favicon placeholder to avoid 404 spam
    path("favicon.ico", lambda request: HttpResponse(status=204)),
    # Static assets emitted by Vite build (css/js/img)
    re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": FRONTEND_BUILD / "assets"}),

    # Django admin & API
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
