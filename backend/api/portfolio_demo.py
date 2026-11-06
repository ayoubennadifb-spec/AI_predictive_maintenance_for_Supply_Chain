"""Public, read-only demo with a restricted synthetic-data viewer session."""
import os
from django.http import JsonResponse
from django.contrib.auth import login

class PortfolioDemoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.getenv("PORTFOLIO_DEMO") != "1":
            return self.get_response(request)
        path = request.path or ""
        if path.startswith("/admin/") or path.startswith("/api/admin/") or path.startswith("/api/users/"):
            return JsonResponse({"error": "Unavailable in portfolio demo"}, status=403)
        # Allow the SPA to discover its read-only demo user, but not login/signup/reset.
        if path.startswith("/api/auth/") and path != "/api/auth/me/":
            return JsonResponse({"error": "Authentication changes disabled in demo"}, status=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            return JsonResponse({"error": "Read-only portfolio demo"}, status=403)
        if path.startswith("/api/") and not request.user.is_authenticated:
            from django.contrib.auth import get_user_model
            demo = get_user_model().objects.filter(username="portfolio_demo").first()
            if demo:
                login(request, demo, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
