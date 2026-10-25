"""First-run initialisation. Only ever adds records; never deletes anything."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import audit
from core.models import Branch, Organization
from core.validation import ActionError


def needs_setup():
    return not get_user_model().objects.exists()


DEFAULT_RULES = [
    ("Employee incentive", "Air Ticket", "% of margin", 5), ("Employee incentive", "Visa", "Fixed per booking", 500),
    ("Employee incentive", "Umrah", "% of margin", 2), ("Employee incentive", "Tour", "% of margin", 4),
    ("Sub-agent commission", "Air Ticket", "% of selling price", 1.5), ("Sub-agent commission", "Visa", "Fixed per passenger", 1000),
    ("Sub-agent commission", "Umrah", "Fixed per passenger", 2000), ("Sub-agent commission", "Tour", "% of selling price", 2),
    ("Supplier commission (earned)", "Air Ticket", "As agreed per ticket with consolidator", None),
]


@transaction.atomic
def initialize(*, org_name, city, branch_name, branch_code, admin_name, username, password, email="", phone=""):
    from accounts.models import Employee
    from finance.ledger import ensure_chart, new_cash_account
    from finance.models import CommissionRule, Period

    User = get_user_model()
    errors = {}
    if User.objects.exists():
        raise ActionError("SafarPro is already set up. Sign in instead.")
    if not org_name.strip():
        errors["org_name"] = "Enter your agency name."
    if not branch_name.strip():
        errors["branch_name"] = "Enter your main branch name."
    if not city.strip():
        errors["city"] = "Enter a city."
    if not branch_code.strip() or len(branch_code.strip()) > 6 or not branch_code.strip().isalnum():
        errors["branch_code"] = "Use 2–6 letters or digits, e.g. LHR."
    if not admin_name.strip():
        errors["admin_name"] = "Enter the administrator's full name."
    if not username.strip() or len(username) > 40:
        errors["username"] = "Choose a username (up to 40 characters)."
    try:
        validate_password(password, User(username=username, first_name=admin_name))
    except ValidationError as e:
        errors["password"] = " ".join(e.messages)
    if errors:
        raise ActionError("Please correct the highlighted fields.", errors)

    ensure_chart()
    org = Organization.get()
    org.name, org.city = org_name.strip(), city.strip()
    org.setup_completed_at = timezone.now()
    org.save()
    branch = Branch.objects.create(code=branch_code.strip().upper(), name=branch_name.strip(), city=city.strip(), cash_account=new_cash_account(city.strip()))
    user = User.objects.create_user(username=username.strip(), password=password, email=email, first_name=admin_name.strip())
    emp = Employee.objects.create(user=user, code="EMP-001", name=admin_name.strip(), role="Administrator", branch=branch, email=email, phone=phone)
    branch.manager = emp
    branch.save()
    for kind, service, basis, rate in DEFAULT_RULES:
        CommissionRule.objects.get_or_create(kind=kind, service=service, defaults=dict(basis=basis, rate=rate))
    t = timezone.localdate()
    Period.objects.get_or_create(name=t.strftime("%B %Y"), defaults=dict(start=t.replace(day=1), end=(t.replace(day=28) + timezone.timedelta(days=4)).replace(day=1) - timezone.timedelta(days=1)))
    audit(user, "Initial setup completed", "Settings", org.name, next=f"Branch {branch.code}, administrator {user.username}", severity="High")
    return user
