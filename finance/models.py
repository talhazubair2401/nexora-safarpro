from django.conf import settings
from django.db import models
from django.utils import timezone
from django.db.models import Q

MONEY = dict(max_digits=14, decimal_places=2)


class Account(models.Model):
    TYPES = ["Asset", "Liability", "Equity", "Income", "Expense"]
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=10)
    group = models.CharField(max_length=30)  # Cash, Bank, Receivable, Payable, Revenue, Direct cost, Operating …

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class Period(models.Model):
    name = models.CharField(max_length=80)
    start = models.DateField()
    end = models.DateField()
    status = models.CharField(max_length=10, default="Open")
    closed_by = models.CharField(max_length=120, blank=True)
    closed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["start"]


class JournalEntry(models.Model):
    """A posted, balanced, immutable accounting entry. Corrections are new entries."""
    date = models.DateField(db_index=True)
    ref = models.CharField(max_length=40, db_index=True)
    memo = models.CharField(max_length=300)
    source = models.CharField(max_length=30)
    booking = models.ForeignKey("operations.Booking", null=True, blank=True, on_delete=models.PROTECT, related_name="entries")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=120)

    class Meta:
        ordering = ["date", "id"]


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(**MONEY, default=0)
    credit = models.DecimalField(**MONEY, default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(debit__gte=0) & Q(credit__gte=0), name="line_non_negative"),
            models.CheckConstraint(condition=Q(debit=0) | Q(credit=0), name="line_one_side"),
        ]


class Payment(models.Model):
    ref = models.CharField(max_length=24, unique=True)
    booking = models.ForeignKey("operations.Booking", on_delete=models.PROTECT, related_name="payments")
    date = models.DateField()
    method = models.CharField(max_length=30)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    amount = models.DecimalField(**MONEY)
    tx_ref = models.CharField(max_length=60, blank=True, db_index=True)
    received_by = models.ForeignKey("accounts.Employee", on_delete=models.PROTECT)
    status = models.CharField(max_length=10, default="Posted")  # Posted | Reversed
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT)
    notes = models.CharField(max_length=300, blank=True)
    prev_balance = models.DecimalField(**MONEY)
    new_balance = models.DecimalField(**MONEY)
    reversed_on = models.DateField(null=True, blank=True)
    reverse_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="payment_positive")]


class SupplierPayment(models.Model):
    ref = models.CharField(max_length=24, unique=True)
    supplier = models.ForeignKey("operations.Supplier", on_delete=models.PROTECT, related_name="payments")
    date = models.DateField()
    amount = models.DecimalField(**MONEY)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    method = models.CharField(max_length=30)
    tx_ref = models.CharField(max_length=60, blank=True)
    by = models.ForeignKey("accounts.Employee", on_delete=models.PROTECT)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="supplier_payment_positive")]


class Expense(models.Model):
    CATEGORIES = {"Office Rent": "6000", "Salaries": "6010", "Utilities": "6020", "Marketing": "6030", "Transport": "6040",
                  "Software": "6050", "Other": "6090"}
    ref = models.CharField(max_length=24, unique=True)
    date = models.DateField()
    category = models.CharField(max_length=30)
    desc = models.CharField(max_length=250)
    amount = models.DecimalField(**MONEY)
    method = models.CharField(max_length=30)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT)
    status = models.CharField(max_length=10, default="Pending")
    submitted_by = models.ForeignKey("accounts.Employee", on_delete=models.PROTECT)
    approved_by = models.CharField(max_length=120, blank=True)
    supplier = models.ForeignKey("operations.Supplier", null=True, blank=True, on_delete=models.PROTECT)
    attachment = models.ForeignKey("crm.Document", null=True, blank=True, on_delete=models.SET_NULL)
    reject_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="expense_positive")]


class Refund(models.Model):
    STAGES = ["Requested", "Under Review", "Awaiting Approval", "Approved", "Processing", "Completed", "Rejected"]
    ref = models.CharField(max_length=24, unique=True)
    booking = models.ForeignKey("operations.Booking", on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT)
    requested = models.DecimalField(**MONEY)
    approved = models.DecimalField(**MONEY, null=True, blank=True)
    cancel_fee = models.DecimalField(**MONEY, default=0)   # value of the booking kept by the agency
    fee = models.DecimalField(**MONEY, default=0)          # refund processing fee (income)
    supplier_credit = models.DecimalField(**MONEY, default=0)
    method = models.CharField(max_length=30)
    reason = models.CharField(max_length=300)
    requested_by = models.CharField(max_length=120)
    approved_by = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, default="Requested")
    date = models.DateField(default=timezone.localdate)
    completed_on = models.DateField(null=True, blank=True)
    reject_reason = models.CharField(max_length=300, blank=True)
    history = models.JSONField(default=list)


class CommissionRule(models.Model):
    KINDS = ["Employee incentive", "Sub-agent commission", "Supplier commission (earned)"]
    BASES = ["% of margin", "% of selling price", "Fixed per booking", "Fixed per passenger"]
    kind = models.CharField(max_length=40)
    service = models.CharField(max_length=20)
    basis = models.CharField(max_length=40)
    rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)


class Commission(models.Model):
    ref = models.CharField(max_length=24, unique=True)
    kind = models.CharField(max_length=40)
    party = models.CharField(max_length=150)
    employee = models.ForeignKey("accounts.Employee", null=True, blank=True, on_delete=models.PROTECT)
    agent = models.ForeignKey("operations.Agent", null=True, blank=True, on_delete=models.PROTECT)
    supplier = models.ForeignKey("operations.Supplier", null=True, blank=True, on_delete=models.PROTECT)
    booking = models.ForeignKey("operations.Booking", on_delete=models.PROTECT, related_name="commissions")
    basis = models.CharField(max_length=120)
    amount = models.DecimalField(**MONEY)
    status = models.CharField(max_length=20, default="Pending")
    date = models.DateField()
    paid_on = models.DateField(null=True, blank=True)
    reverse_reason = models.CharField(max_length=300, blank=True)


class CashClosing(models.Model):
    ref = models.CharField(max_length=30, unique=True)
    date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    opening = models.DecimalField(**MONEY)
    receipts = models.DecimalField(**MONEY)
    payments = models.DecimalField(**MONEY)
    expected = models.DecimalField(**MONEY)
    counted = models.DecimalField(**MONEY)
    diff = models.DecimalField(**MONEY)
    status = models.CharField(max_length=40)
    note = models.CharField(max_length=300, blank=True)
    by = models.CharField(max_length=120)
    adj_posted = models.BooleanField(default=False)
    adj_reason = models.CharField(max_length=300, blank=True)


class BankMatch(models.Model):
    entry = models.OneToOneField(JournalEntry, on_delete=models.CASCADE, related_name="bank_match")
    matched_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    matched_at = models.DateTimeField(auto_now_add=True)
