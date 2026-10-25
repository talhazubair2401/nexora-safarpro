from django.contrib.staticfiles.views import serve as static_serve
from django.urls import path, re_path

from accounts import views as auth_views
from web import views

urlpatterns = [
    path("", views.app, name="app"),
    path("setup/", auth_views.first_run_setup, name="setup"),
    path("login/", auth_views.login_view, name="login"),
    path("logout/", auth_views.logout_view, name="logout"),
    path("demo/login/", auth_views.demo_login, name="demo_login"),
    path("api/ping", views.ping, name="ping"),
    path("api/state", views.state, name="state"),
    path("api/action/<str:name>", views.action, name="action"),
    path("documents/<int:doc_id>/file", views.document_file, name="document_file"),
    path("backups/<str:filename>", views.backup_download, name="backup_download"),
    # Static assets are bundled with the app and served locally — no CDN, works offline.
    re_path(r"^static/(?P<path>.*)$", static_serve, {"insecure": True}),
]

handler404 = "web.views.not_found"
handler500 = "web.views.server_error"
