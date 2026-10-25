from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.cache import cache
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from core.audit import audit
from core.setup import initialize, needs_setup
from core.validation import ActionError

MAX_ATTEMPTS = 5
LOCK_SECONDS = 300


@csrf_protect
def first_run_setup(request):
    if not needs_setup():
        return redirect("login")
    ctx = {"v": {}, "errors": {}}
    if request.method == "POST":
        p = request.POST
        ctx["v"] = {k: p.get(k, "") for k in ("org_name", "city", "branch_name", "branch_code", "admin_name", "username", "email")}
        if p.get("password") != p.get("password2"):
            ctx["errors"] = {"password2": "The two passwords do not match."}
        else:
            try:
                user = initialize(org_name=p.get("org_name", ""), city=p.get("city", ""), branch_name=p.get("branch_name", ""),
                                  branch_code=p.get("branch_code", ""), admin_name=p.get("admin_name", ""), username=p.get("username", ""),
                                  password=p.get("password", ""), email=p.get("email", ""))
                if p.get("sample") == "on":
                    from web.sample import load_sample_data
                    load_sample_data(user)
                login(request, user)
                return redirect("app")
            except ActionError as e:
                ctx["errors"] = e.errors or {"general": e.message}
    return render(request, "web/setup.html", ctx)


@csrf_protect
def login_view(request):
    if needs_setup():
        return redirect("setup")
    if request.user.is_authenticated:
        return redirect("app")
    ctx = {"error": "", "username": ""}
    if settings.DEMO_MODE:
        from web.demo import DEMO_ACCOUNTS, next_reset
        ctx["demo"] = [{"username": u, "role": r, "name": n, "desc": d, "ini": "".join(w[0] for w in n.split()[:2])} for u, r, n, d in DEMO_ACCOUNTS]
        ctx["demo_reset"] = next_reset()
        return render(request, "web/login.html", ctx)
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        ctx["username"] = username
        key = f"login-fail:{username.lower()}"
        fails = cache.get(key, 0)
        if fails >= MAX_ATTEMPTS:
            ctx["error"] = "Too many failed attempts. Wait 5 minutes and try again."
        else:
            user = authenticate(request, username=username, password=request.POST.get("password") or "")
            emp = getattr(user, "employee", None) if user else None
            if user and (emp is None or emp.status != "Active") and not user.is_superuser:
                ctx["error"] = "This account is suspended. Ask an administrator to reactivate it."
            elif user:
                cache.delete(key)
                login(request, user)
                audit(user, "Signed in", "Employees", username, severity="Low")
                return redirect(request.GET.get("next") if (request.GET.get("next") or "").startswith("/") else "app")
            else:
                cache.set(key, fails + 1, LOCK_SECONDS)
                ctx["error"] = "Incorrect username or password."
    return render(request, "web/login.html", ctx)


def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if request.user.is_authenticated:
        audit(request.user, "Signed out", "Employees", request.user.username, severity="Low")
    logout(request)
    return redirect("login")


@require_POST
@csrf_protect
def demo_login(request):
    """Public demo only: one-click sign-in as a demo role (demo accounts have no usable password)."""
    from web.demo import DEMO_USERNAMES
    username = request.POST.get("username") or ""
    if not settings.DEMO_MODE or username not in DEMO_USERNAMES:
        return redirect("login")
    user = get_user_model().objects.filter(username=username, is_active=True).first()
    if not user:
        return redirect("login")
    if request.user.is_authenticated:
        logout(request)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    audit(user, "Signed in (demo)", "Employees", username, severity="Low")
    return redirect("app")
