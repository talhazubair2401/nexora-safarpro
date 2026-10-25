"""Role-based permissions, enforced on the server for every API action and data read."""
from .models import ROLES

PERM_AREAS = [
    ("customer", "Customers"), ("enquiry", "Enquiries & quotations"), ("booking", "Bookings"), ("ticket", "Air tickets"),
    ("visa", "Visa applications"), ("umrah", "Umrah, tours, hotels"), ("payment", "Payments & receipts"),
    ("expense", "Expenses"), ("refund", "Refunds"), ("supplier", "Suppliers & supplier payments"),
    ("journal", "Accounting, journals & periods"), ("commission", "Commissions"), ("cash", "Cash & bank closing"),
    ("agent", "Sub-agents"), ("settings", "Settings, users & backups"),
]
PERM_ACTS = ["view", "create", "edit", "approve", "reverse", "export", "delete"]


def _g(areas, acts):
    return {f"{a}.{x}" for a in areas for x in acts}


ALL = _g([a for a, _ in PERM_AREAS], PERM_ACTS)
OPS = ["customer", "enquiry", "booking", "ticket", "visa", "umrah"]
FIN = ["payment", "expense", "refund", "supplier", "journal", "commission", "cash"]
VIEW_ALL = _g([a for a, _ in PERM_AREAS], ["view"])

ROLE_PERMS = {
    "Owner": ALL,
    "Administrator": ALL,
    "Branch Manager": VIEW_ALL - {"settings.view"} | _g(OPS, ["create", "edit", "approve", "export"])
        | _g(["payment", "expense", "refund", "cash", "agent", "supplier"], ["create", "edit", "approve", "export"]) | {"payment.reverse"},
    "Accountant": VIEW_ALL - {"settings.view"} | _g(FIN, ["create", "edit", "approve", "reverse", "export"])
        | {"customer.export", "booking.export", "agent.create", "agent.edit"},
    "Ticketing Officer": _g(["customer", "enquiry", "booking", "ticket", "visa", "umrah", "payment", "refund", "supplier"], ["view"])
        | _g(["customer", "enquiry", "booking", "ticket"], ["create", "edit"]) | {"payment.create", "refund.create"},
    "Visa Officer": _g(["customer", "enquiry", "booking", "visa", "payment"], ["view"])
        | _g(["customer", "enquiry", "visa"], ["create", "edit"]) | {"booking.create", "payment.create"},
    "Tour Operations Officer": _g(["customer", "enquiry", "booking", "umrah", "payment", "supplier"], ["view"])
        | _g(["customer", "enquiry", "booking", "umrah"], ["create", "edit"]) | {"payment.create"},
    "Receptionist": _g(["customer", "enquiry", "booking", "ticket", "visa", "umrah"], ["view"])
        | _g(["customer", "enquiry"], ["create", "edit"]) | {"booking.create"},
    "Read-Only Auditor": VIEW_ALL | _g([a for a, _ in PERM_AREAS], ["export"]),
}
assert set(ROLE_PERMS) == set(ROLES)


def role_of(user):
    if not user or not user.is_authenticated:
        return None
    emp = getattr(user, "employee", None)
    if emp is not None:
        return emp.role if emp.status == "Active" else None
    return "Administrator" if user.is_superuser else None


def perms_for(user):
    return ROLE_PERMS.get(role_of(user), set())


def has_perm(user, perm):
    return perm in perms_for(user)
