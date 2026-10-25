from django.conf import settings


def branding(request):
    return {"APP_NAME": settings.APP_NAME, "APP_VERSION": settings.APP_VERSION, "COMPANY": "Nexora", "DEMO_MODE": settings.DEMO_MODE}
