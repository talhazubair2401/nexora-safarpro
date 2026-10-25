from django.shortcuts import redirect

from core.setup import needs_setup


class SetupRequiredMiddleware:
    """Until the first administrator exists, every page goes to the first-run setup screen."""

    ALLOWED = ("/setup/", "/static/", "/api/ping")

    def __init__(self, get_response):
        self.get_response = get_response
        self.done = False

    def __call__(self, request):
        if not self.done:
            if needs_setup():
                if not request.path.startswith(self.ALLOWED):
                    return redirect("setup")
            else:
                self.done = True
        return self.get_response(request)


class DemoResetMiddleware:
    """Public demo only: builds the fictional demo data on first use and rebuilds it when it is too old."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        if settings.DEMO_MODE and not request.path.startswith("/static/"):
            from web.demo import ensure_fresh
            ensure_fresh()
        return self.get_response(request)
