import json
import logging

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from accounts.permissions import has_perm
from core.models import IdempotencyKey
from core.validation import ActionError
from crm.models import Document

from .actions import ACTIONS, Ctx
from .state import build_state

log = logging.getLogger("safarpro")


@login_required
def app(request):
    return render(request, "web/app.html")


@require_GET
def ping(request):
    return JsonResponse({"ok": True, "app": settings.APP_NAME, "version": settings.APP_VERSION})


def _auth_json(request):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "message": "Your session has ended. Please sign in again.", "login": True}, status=401)
    emp = getattr(request.user, "employee", None)
    if emp is not None and emp.status != "Active":
        logout(request)
        return JsonResponse({"ok": False, "message": "Your account has been suspended.", "login": True}, status=401)
    return None


@require_GET
def state(request):
    denied = _auth_json(request)
    if denied:
        return denied
    return JsonResponse({"ok": True, "state": build_state(request.user)})


def demo_blocked(name, data):
    from web.demo import BLOCKED_ACTIONS
    if name in BLOCKED_ACTIONS:
        return BLOCKED_ACTIONS[name]
    if name in ("employee.status", "employee.role"):
        from accounts.models import Employee
        eid = str(data.get("id") or "")
        e = Employee.objects.filter(pk=int(eid)).first() if eid.isdigit() else None
        if e and e.user_id:
            return "Demo sign-in accounts can't be suspended or have their role changed. Try it on an employee without a login."
    return None


@require_POST
def action(request, name):
    denied = _auth_json(request)
    if denied:
        return denied
    entry = ACTIONS.get(name)
    if not entry:
        return JsonResponse({"ok": False, "message": "Unknown action."}, status=404)
    fn, perm = entry
    try:
        if request.content_type and request.content_type.startswith("multipart/"):
            data = json.loads(request.POST.get("payload") or "{}")
        else:
            data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"ok": False, "message": "The request could not be read."}, status=400)
    if settings.DEMO_MODE:
        blocked = demo_blocked(name, data)
        if blocked:
            return JsonResponse({"ok": False, "message": blocked}, status=403)
    required = perm(data) if callable(perm) else perm
    if required and not has_perm(request.user, required):
        return JsonResponse({"ok": False, "message": "Your role does not allow this action."}, status=403)
    key = str(data.pop("_key", "") or "")[:64]
    try:
        with transaction.atomic():
            if key:
                prev = IdempotencyKey.objects.filter(key=key).first()
                if prev:
                    return JsonResponse({"ok": True, "result": prev.result, "duplicate": True, "state": build_state(request.user)})
            result = fn(Ctx(request.user, request.FILES), data) or {}
            if key:
                IdempotencyKey.objects.create(key=key, action=name, result=result)
    except ActionError as e:
        return JsonResponse({"ok": False, "message": e.message, "errors": e.errors}, status=e.status)
    except Exception:
        log.exception("Action %s failed", name)
        return JsonResponse({"ok": False, "message": "Something went wrong and nothing was saved. Details are in the SafarPro log file."}, status=500)
    return JsonResponse({"ok": True, "result": result, "state": build_state(request.user)})


@login_required
def document_file(request, doc_id):
    if not has_perm(request.user, "customer.view"):
        raise Http404
    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        raise Http404
    path = (settings.DOCUMENTS_ROOT / doc.stored_name).resolve()
    if settings.DOCUMENTS_ROOT.resolve() not in path.parents or not path.exists():
        raise Http404
    inline = request.GET.get("download") != "1" and doc.content_type in ("application/pdf", "image/png", "image/jpeg", "image/webp")
    resp = FileResponse(open(path, "rb"), content_type=doc.content_type, as_attachment=not inline, filename=doc.original_name)
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, no-store"
    return resp


@login_required
def backup_download(request, filename):
    if settings.DEMO_MODE or not has_perm(request.user, "settings.view"):
        raise Http404
    if "/" in filename or "\\" in filename or not filename.startswith("SafarPro-backup-") or not filename.endswith(".zip"):
        raise Http404
    path = settings.BACKUP_ROOT / filename
    if not path.exists():
        raise Http404
    return FileResponse(open(path, "rb"), as_attachment=True, filename=filename)


def not_found(request, exception=None):
    return render(request, "web/error.html", {"code": 404, "title": "Page not found", "text": "That page doesn't exist in SafarPro."}, status=404)


def server_error(request):
    return render(request, "web/error.html", {"code": 500, "title": "Something went wrong", "text": "The error was logged. Your data has not been changed."}, status=500)
