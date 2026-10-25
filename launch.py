"""
Nexora SafarPro launcher (started by run_safarpro.bat).

1. Checks Python and installed packages.
2. Backs up the database if an update needs to change it, then applies migrations.
3. Starts the local server on 127.0.0.1 (never reachable from other computers).
4. Opens SafarPro in the default browser.
Nothing here ever deletes or resets data.
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "safarpro.settings")


def fail(msg, hint=""):
    print("\n[ERROR] " + msg)
    if hint:
        print("        " + hint)
    sys.exit(1)


def port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def is_safarpro(host, port):
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/ping", timeout=1.5) as r:
            return json.loads(r.read().decode()).get("app", "").endswith("SafarPro")
    except Exception:
        return False


def open_browser_when_ready(url, host, port):
    for _ in range(120):
        if port_open(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.25)
    print("[WARN] The server is taking long to start. Open this address manually: " + url)


def main():
    print("=" * 62)
    print("  Nexora SafarPro — local travel agency management")
    print("=" * 62)
    if sys.version_info < (3, 10):
        fail(f"Python 3.10 or newer is required (found {sys.version.split()[0]}).", "Install Python from python.org, then run setup_windows.bat again.")
    try:
        import django
    except ImportError:
        fail("Django is not installed in this environment.", "Run setup_windows.bat first.")
    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    host, port = settings.SERVER_HOST, settings.SERVER_PORT
    if host not in ("127.0.0.1", "localhost"):
        print(f"[WARN] SAFARPRO_HOST is set to {host}. Other computers on your network may be able to reach SafarPro.")
    if port_open(host, port):
        if is_safarpro(host, port):
            url = f"http://{host}:{port}/"
            print(f"SafarPro is already running. Opening {url}")
            webbrowser.open(url)
            return
        for p in range(port + 1, port + 20):
            if not port_open(host, p):
                print(f"[INFO] Port {port} is used by another program — using port {p} instead.")
                port = p
                os.environ["SAFARPRO_PORT"] = str(p)
                settings.SERVER_PORT = p
                break
        else:
            fail(f"Ports {port}–{port + 19} are all in use.", "Close other programs or set SAFARPRO_PORT to a free port.")

    print(f"Data folder : {settings.DATA_ROOT}")
    print(f"Database    : {settings.DB_PATH}")
    try:
        call_command("safe_migrate")
        call_command("check", verbosity=0)
    except SystemExit:
        raise
    except Exception as e:
        fail(f"Startup check failed: {e}", f"Your data has not been changed. See the log in {settings.LOG_DIR}")

    url = f"http://{host}:{port}/"
    print("\nSafarPro is running at " + url)
    print("Keep this window open while you work. To stop SafarPro, close this window or press Ctrl+C.\n")
    if os.environ.get("SAFARPRO_NO_BROWSER") != "1":
        threading.Thread(target=open_browser_when_ready, args=(url, host, port), daemon=True).start()
    from safarpro.wsgi import application
    try:
        from waitress import serve
        serve(application, host=host, port=port, threads=8, ident="Nexora SafarPro", clear_untrusted_proxy_headers=True)
    except ImportError:
        print("[INFO] waitress not installed — using Django's built-in server.")
        call_command("runserver", f"{host}:{port}", "--noreload", "--insecure")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSafarPro stopped. Your data is saved.")
