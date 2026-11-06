"""Public read-only demo, with automatic restricted demo session."""
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
        if path.startswith("/admin/"):
            return JsonResponse({"error":"Disabled in portfolio demo"}, status=403)
        if request.method not in ("GET","HEAD","OPTIONS"):
            return JsonResponse({"error":"Read-only portfolio demo"}, status=403)
        if path.startswith("/api/") and not request.user.is_authenticated:
            from django.contrib.auth import get_user_model
            demo = get_user_model().objects.filter(username="portfolio_demo").first()
            if demo:
                login(request, demo, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
