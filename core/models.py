from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F


def default_methods():
    return ["Cash", "Bank Transfer", "Card", "Digital Payment"]


def default_visa_docs():
    return [
        "Passport (original, 6+ months validity)", "CNIC copy", "Photographs (white background)",
        "Bank statement — 6 months", "Employment or business letter", "Travel itinerary",
        "Hotel reservation", "Cover letter",
    ]


def default_notif_prefs():
    cats = ["Payments", "Visa Deadlines", "Travel Departures", "Supplier Payments", "Booking Updates", "System Alerts"]
    return {c: {"app": 1, "email": 0, "wa": 0} for c in cats}


class Organization(models.Model):
    """Single row holding the agency profile and financial/workflow rules."""
    name = models.CharField(max_length=120, default="My Travel Agency")
    city = models.CharField(max_length=80, blank=True)
    address = models.CharField(max_length=250, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.CharField(max_length=120, blank=True)
    ntn = models.CharField("NTN / tax ID", max_length=40, blank=True)
    currency = models.CharField(max_length=3, default="PKR")
    credit_days = models.PositiveIntegerField(default=14)
    expense_approval_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("25000"))
    refund_approval_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("50000"))
    discount_limit = models.PositiveIntegerField(default=5)
    allow_overpayment = models.BooleanField(default=False)
    receipt_prefix = models.CharField(max_length=12, default="SP-RC-")
    booking_prefix = models.CharField(max_length=12, default="SP-BK-")
    payment_methods = models.JSONField(default=default_methods)
    visa_docs = models.JSONField(default=default_visa_docs)
    visa_docs_required = models.BooleanField(default=True)
    notification_prefs = models.JSONField(default=default_notif_prefs)
    bank_statement_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    sample_data = models.BooleanField(default=False)
    setup_completed_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def get(cls):
        obj = cls.objects.order_by("id").first()
        return obj or cls.objects.create()

    def __str__(self):
        return self.name


class Branch(models.Model):
    code = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=120)
    city = models.CharField(max_length=80)
    address = models.CharField(max_length=250, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, default="Active")
    cash_account = models.ForeignKey("finance.Account", on_delete=models.PROTECT, related_name="branches")
    manager = models.ForeignKey("accounts.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_branches")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class Sequence(models.Model):
    """Gap-free counters for receipt / booking / voucher numbers."""
    key = models.CharField(max_length=40, unique=True)
    value = models.PositiveIntegerField(default=0)

    @classmethod
    def next(cls, key, start=0):
        cls.objects.get_or_create(key=key, defaults={"value": start})
        cls.objects.filter(key=key).update(value=F("value") + 1)
        return cls.objects.get(key=key).value


class AuditLog(models.Model):
    SEVERITIES = ["Info", "Low", "Medium", "High", "Critical"]
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    user_name = models.CharField(max_length=120)
    action = models.CharField(max_length=120)
    module = models.CharField(max_length=40, db_index=True)
    ref = models.CharField(max_length=120, blank=True)
    prev = models.TextField(blank=True)
    next = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    severity = models.CharField(max_length=10, default="Info")

    class Meta:
        ordering = ["-at", "-id"]


class NotificationState(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=120)
    read = models.BooleanField(default=True)

    class Meta:
        unique_together = [("user", "key")]


class IdempotencyKey(models.Model):
    """Prevents a double-click or network retry from creating the same record twice."""
    key = models.CharField(max_length=64, unique=True)
    action = models.CharField(max_length=60)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
