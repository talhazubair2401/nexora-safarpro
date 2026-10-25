"""
Nexora SafarPro — Django settings.

Business data (database, uploaded documents, backups, logs) lives OUTSIDE the
source folder, in a persistent per-user directory:

    Windows : %LOCALAPPDATA%\\Nexora\\SafarPro\\
    Others  : ~/.local/share/Nexora/SafarPro/

Override with the SAFARPRO_DATA_DIR environment variable.
Nothing in this file ever deletes or recreates the database.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_NAME = "Nexora SafarPro"
APP_VERSION = "1.0.0"


def _default_data_root() -> Path:
    env = os.environ.get("SAFARPRO_DATA_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Nexora" / "SafarPro"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "Nexora" / "SafarPro"


DATA_ROOT = _default_data_root()
DB_DIR = DATA_ROOT / "data"
DOCUMENTS_ROOT = DATA_ROOT / "documents"
BACKUP_ROOT = DATA_ROOT / "backups"
LOG_DIR = DATA_ROOT / "logs"
for _d in (DB_DIR, DOCUMENTS_ROOT, BACKUP_ROOT, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "safarpro.sqlite3"

# Secret key: generated once per installation and kept with the data (never hard-coded).
_key_file = DB_DIR / "secret_key.txt"
if _key_file.exists() and _key_file.read_text().strip():
    SECRET_KEY = _key_file.read_text().strip()
else:
    SECRET_KEY = secrets.token_urlsafe(50)
    _key_file.write_text(SECRET_KEY)

DEBUG = os.environ.get("SAFARPRO_DEBUG") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

# Public online demo (portfolio). OFF by default — the Windows install never uses it.
# When on: fictional data only, one-click role sign-in, data rebuilt automatically every
# DEMO_RESET_HOURS, and password/backup actions disabled.
DEMO_MODE = os.environ.get("SAFARPRO_DEMO") == "1"
DEMO_RESET_HOURS = float(os.environ.get("SAFARPRO_DEMO_RESET_HOURS", "24"))
_extra_hosts = [h.strip() for h in os.environ.get("SAFARPRO_ALLOWED_HOSTS", "").split(",") if h.strip()]
ALLOWED_HOSTS += _extra_hosts
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in _extra_hosts]
SERVER_HOST = os.environ.get("SAFARPRO_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("SAFARPRO_PORT", "8765"))

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "accounts",
    "crm",
    "operations",
    "finance",
    "web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "web.middleware.DemoResetMiddleware",
    "web.middleware.SetupRequiredMiddleware",
]

ROOT_URLCONF = "safarpro.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "web.context.branding",
    ]},
}]
WSGI_APPLICATION = "safarpro.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_PATH,
        "OPTIONS": {
            # WAL keeps reads working while a write is in progress; IMMEDIATE makes
            # write transactions take the lock up front (no half-finished postings).
            "init_command": "PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;",
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = DATA_ROOT / "static-cache"  # not used for serving; kept out of the source tree

# Uploads
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".docx", ".xlsx"}
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Session & CSRF hardening for a local single-PC app
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_AGE = 12 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_USE_SESSIONS = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if os.environ.get("SAFARPRO_HTTPS") == "1":  # served behind an HTTPS proxy (online demo)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "file": {"class": "logging.handlers.RotatingFileHandler", "filename": str(LOG_DIR / "safarpro.log"),
                 "maxBytes": 2_000_000, "backupCount": 5, "formatter": "plain", "encoding": "utf-8"},
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["file", "console"], "level": "WARNING"},
    "loggers": {"safarpro": {"handlers": ["file", "console"], "level": "INFO", "propagate": False}},
}
