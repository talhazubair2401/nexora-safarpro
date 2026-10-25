"""
Public online demo (portfolio) — only active when SAFARPRO_DEMO=1.

The demo database is rebuilt from fictional sample data:
  * the first time the demo server receives a request, and
  * automatically once the data is older than DEMO_RESET_HOURS.
Visitors sign in with one click as one of several roles; demo accounts have
no usable password, so nobody can lock them, change them or guess them.

This module refuses to run unless DEMO_MODE is on, so it can never touch a
real installation's data.
"""
import datetime as dt
import logging
import secrets
import shutil
import threading
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import transaction

log = logging.getLogger("safarpro")

# (username, role, employee name, one-line description shown on the sign-in page)
DEMO_ACCOUNTS = [
    ("demo-owner", "Administrator", "Ahmed Khan", "Full access: every module, reports, settings and staff."),
    ("demo-manager", "Branch Manager", "Kamran Shah", "Runs a branch: bookings, approvals and branch reports."),
    ("demo-accountant", "Accountant", "Sana Iqbal", "Payments, refunds, expenses, journal and financial reports."),
    ("demo-visa", "Visa Officer", "Mehwish Akhtar", "Visa files, documents and customer records."),
    ("demo-reception", "Receptionist", "Zain Abbas", "Front desk: customers and enquiries. No money or accounts."),
]
DEMO_USERNAMES = {a[0] for a in DEMO_ACCOUNTS}
BLOCKED_ACTIONS = {
    "me.password": "Password changes are turned off in the public demo.",
    "employee.login": "Creating logins and resetting passwords is turned off in the public demo.",
    "backup.create": "Backups are turned off in the public demo. In the desktop edition this creates a verified .zip backup.",
}

_lock = threading.Lock()
_last_check = 0.0


def _marker():
    return settings.DATA_ROOT / "demo_built_at.txt"


def built_at():
    try:
        return dt.datetime.fromisoformat(_marker().read_text().strip())
    except (OSError, ValueError):
        return None


def next_reset():
    b = built_at()
    return b + dt.timedelta(hours=settings.DEMO_RESET_HOURS) if b else None


def is_stale():
    b = built_at()
    return b is None or dt.datetime.now() - b >= dt.timedelta(hours=settings.DEMO_RESET_HOURS)


def build_demo():
    """Wipe and rebuild the demo database. Only allowed in demo mode."""
    if not settings.DEMO_MODE:
        raise RuntimeError("build_demo() is only allowed when SAFARPRO_DEMO=1.")
    from accounts.models import Employee
    from core.setup import initialize
    from web.sample import load_sample_data

    call_command("migrate", interactive=False, verbosity=0)
    call_command("flush", interactive=False, verbosity=0)
    if settings.DOCUMENTS_ROOT.exists():
        shutil.rmtree(settings.DOCUMENTS_ROOT, ignore_errors=True)
    settings.DOCUMENTS_ROOT.mkdir(parents=True, exist_ok=True)
    cache.clear()

    User = get_user_model()
    owner_user, owner_role, owner_name, _ = DEMO_ACCOUNTS[0]
    with transaction.atomic():
        user = initialize(org_name="Nexora Demo Travels", city="Lahore", branch_name="Head Office", branch_code="LHR",
                          admin_name=owner_name, username=owner_user, password=secrets.token_urlsafe(24),
                          email="owner@example.com")
        user.set_unusable_password()
        user.save()
        load_sample_data(user)
        for username, role, name, _ in DEMO_ACCOUNTS[1:]:
            emp = Employee.objects.filter(name=name, role=role).first()
            if not emp:
                continue
            u = User(username=username, first_name=name, email=emp.email or "")
            u.set_unusable_password()
            u.save()
            emp.user = u
            emp.save(update_fields=["user"])
    _marker().write_text(dt.datetime.now().isoformat(timespec="seconds"))
    log.info("Demo data rebuilt")


def ensure_fresh():
    """Called on requests; rebuilds when the demo data is missing or too old (checked at most every 30 s)."""
    global _last_check
    now = time.monotonic()
    if now - _last_check < 30:
        return
    with _lock:
        if time.monotonic() - _last_check < 30:
            return
        try:
            if is_stale():
                build_demo()
        finally:
            _last_check = time.monotonic()
