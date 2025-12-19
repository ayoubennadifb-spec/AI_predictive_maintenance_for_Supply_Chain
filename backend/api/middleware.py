from django.http import JsonResponse


class ApiAuthMiddleware:
    """
    Enforce authentication for all `/api/*` endpoints except `/api/auth/*`.

    The frontend is a SPA served by Django on the same origin, so Django sessions
    are the simplest auth mechanism. For dev setups where the frontend runs on a
    different origin, the client must send cookies with `credentials: 'include'`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""

        # Let CORS preflight through and never block non-API paths.
        if request.method == "OPTIONS" or not path.startswith("/api/"):
            return self.get_response(request)

        # Allow auth endpoints (login, signup, forgot/reset, etc).
        if path.startswith("/api/auth/"):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return JsonResponse({"error": "Not authenticated", "code": "not_authenticated"}, status=401)

        return self.get_response(request)

