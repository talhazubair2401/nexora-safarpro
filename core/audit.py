from .models import AuditLog


def user_label(user):
    if not user or not getattr(user, "is_authenticated", False):
        return "System"
    emp = getattr(user, "employee", None)
    return emp.name if emp else (user.get_full_name() or user.username)


def audit(user, action, module, ref="", prev="", next="", reason="", severity="Info"):
    """Append-only audit record. Never updated or deleted by the application."""
    return AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        user_name=user_label(user), action=action, module=module, ref=str(ref)[:120],
        prev=str(prev or "")[:2000], next=str(next or "")[:2000], reason=str(reason or "")[:2000], severity=severity,
    )
