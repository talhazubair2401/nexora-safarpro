"""
Financial engine for Nexora SafarPro.

Every money event posts a balanced, immutable JournalEntry:

  Booking confirmed      Dr 1100 Receivable / Cr revenue        (selling price)
                         Dr direct cost     / Cr 2000 Payable    (supplier cost)
  Supplier cost changed  difference between Payable and direct cost (dated today)
  Booking cancelled      Dr 4090 Cancellations / Cr 1100        (price − cancellation fee kept)
                         Dr 2000 Payable / Cr direct cost        (supplier credit note, if any)
  Customer receipt       Dr cash/bank / Cr 1100
  Receipt reversed       Dr 1100 / Cr cash/bank                 (original stays on record)
  Refund paid            Dr 1100 / Cr cash/bank   + fee: Dr 1100 / Cr 4040
  Supplier payment       Dr 2000 / Cr cash/bank
  Expense approved       Dr expense / Cr cash/bank
  Commission paid        Dr 6060 / Cr bank
  Cash over/short        Dr/Cr 6095 against the cash account
  Manual journal         as entered (control accounts 1100/2000 excluded)

Revenue and profit in reports therefore come from posted entries, so cancellations,
refund fees and cost corrections are always reflected.
"""
import datetime
from decimal import Decimal

from django.db.models import Max, Sum
from django.utils import timezone

from core.validation import ActionError, D

ZERO = Decimal("0.00")

DEFAULT_ACCOUNTS = [
    ("1010", "Main Bank Current Account", "Asset", "Bank"),
    ("1011", "Digital Collections Wallet", "Asset", "Bank"),
    ("1100", "Accounts Receivable (control)", "Asset", "Receivable"),
    ("1200", "Supplier Advances", "Asset", "Other"),
    ("2000", "Accounts Payable (control)", "Liability", "Payable"),
    ("2100", "Customer Advances", "Liability", "Other"),
    ("2200", "Other Liabilities", "Liability", "Other"),
    ("3000", "Owner Capital", "Equity", "Equity"),
    ("3100", "Retained Earnings", "Equity", "Equity"),
    ("4000", "Ticketing Revenue", "Income", "Revenue"),
    ("4010", "Visa Service Revenue", "Income", "Revenue"),
    ("4020", "Umrah Service Revenue", "Income", "Revenue"),
    ("4030", "Tour Revenue", "Income", "Revenue"),
    ("4040", "Other Service Revenue", "Income", "Revenue"),
    ("4090", "Cancellations & Refund Adjustments", "Income", "Contra revenue"),
    ("5000", "Cost of Air Tickets", "Expense", "Direct cost"),
    ("5010", "Visa Processing Costs", "Expense", "Direct cost"),
    ("5020", "Umrah Package Costs", "Expense", "Direct cost"),
    ("5030", "Tour Costs", "Expense", "Direct cost"),
    ("5040", "Hotel & Other Direct Costs", "Expense", "Direct cost"),
    ("6000", "Office Rent", "Expense", "Operating"),
    ("6010", "Salaries", "Expense", "Operating"),
    ("6020", "Utilities", "Expense", "Operating"),
    ("6030", "Marketing", "Expense", "Operating"),
    ("6040", "Transport", "Expense", "Operating"),
    ("6050", "Software", "Expense", "Operating"),
    ("6060", "Staff Incentives & Commissions", "Expense", "Operating"),
    ("6090", "Other Operating Expenses", "Expense", "Operating"),
    ("6095", "Cash Over / Short", "Expense", "Operating"),
]
SVC_ACCTS = {
    "Air Ticket": ("4000", "5000"), "Visa": ("4010", "5010"), "Umrah": ("4020", "5020"), "Tour": ("4030", "5030"),
    "Hotel": ("4040", "5040"), "Transport": ("4040", "5040"), "Other": ("4040", "5040"),
}
CONTROL_ACCOUNTS = {"1100", "2000"}
POSTED_STATUSES = {"Confirmed", "Completed", "Cancelled", "Refunded"}


def today():
    return timezone.localdate()


def ensure_chart():
    from .models import Account
    for code, name, typ, group in DEFAULT_ACCOUNTS:
        Account.objects.get_or_create(code=code, defaults=dict(name=name, type=typ, group=group))


def new_cash_account(city):
    """Each branch gets its own cash-in-hand account (1000–1009)."""
    from .models import Account
    used = set(Account.objects.filter(code__startswith="100").values_list("code", flat=True))
    for n in range(1000, 1010):
        if str(n) not in used:
            return Account.objects.create(code=str(n), name=f"Cash in Hand — {city}", type="Asset", group="Cash")
    raise ActionError("No free cash account codes are left (maximum 10 branches).")


def closed_until():
    from .models import Period
    return Period.objects.filter(status="Closed").aggregate(m=Max("end"))["m"]


def assert_open(date, field="date"):
    cu = closed_until()
    if cu and date <= cu:
        raise ActionError(f"This date is in a closed financial period (closed up to {cu:%d %b %Y}).", {field: f"Period closed up to {cu:%d %b %Y}."})
    if date > today():
        raise ActionError("Transactions cannot be dated in the future.", {field: "Date is in the future."})


def post(date, ref, memo, source, lines, user=None, booking=None):
    from core.audit import user_label
    from .models import Account, JournalEntry, JournalLine
    clean = []
    for code, dr, cr in lines:
        dr, cr = D(dr), D(cr)
        if dr < 0 or cr < 0:
            raise ActionError("Journal amounts cannot be negative.")
        if dr and cr:
            raise ActionError("A journal line can have a debit or a credit, not both.")
        if dr or cr:
            clean.append((code, dr, cr))
    tdr, tcr = sum(l[1] for l in clean), sum(l[2] for l in clean)
    if not clean or tdr != tcr or tdr == 0:
        raise ActionError(f"Journal does not balance (debits {tdr:,.2f}, credits {tcr:,.2f}).")
    assert_open(date)
    accts = {a.code: a for a in Account.objects.filter(code__in=[l[0] for l in clean])}
    missing = [l[0] for l in clean if l[0] not in accts]
    if missing:
        raise ActionError(f"Unknown account {missing[0]}.")
    e = JournalEntry.objects.create(date=date, ref=ref, memo=memo[:300], source=source, booking=booking, created_by=user_label(user))
    JournalLine.objects.bulk_create([JournalLine(entry=e, account=accts[c], debit=dr, credit=cr) for c, dr, cr in clean])
    return e


def account_for_method(method, branch):
    from .models import Account
    if method == "Cash":
        return branch.cash_account
    return Account.objects.get(code="1011" if method == "Digital Payment" else "1010")


def account_balance(code, upto=None, start=None):
    """Natural balance (debit-positive for assets/expenses, credit-positive otherwise)."""
    from .models import Account, JournalLine
    a = Account.objects.get(code=code)
    qs = JournalLine.objects.filter(account=a)
    if upto:
        qs = qs.filter(entry__date__lte=upto)
    if start:
        qs = qs.filter(entry__date__gte=start)
    s = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    d, c = s["d"] or ZERO, s["c"] or ZERO
    return d - c if a.type in ("Asset", "Expense") else c - d


# ---------- Customer balances (single source of truth) ----------

def paid_map(booking_ids=None):
    from .models import Payment
    qs = Payment.objects.filter(status="Posted")
    if booking_ids is not None:
        qs = qs.filter(booking_id__in=booking_ids)
    return {r["booking"]: r["t"] for r in qs.values("booking").annotate(t=Sum("amount"))}


def refund_map(booking_ids=None):
    from .models import Refund
    qs = Refund.objects.filter(status="Completed")
    if booking_ids is not None:
        qs = qs.filter(booking_id__in=booking_ids)
    out = {}
    for r in qs.values("booking", "approved", "fee"):
        out[r["booking"]] = out.get(r["booking"], ZERO) + (r["approved"] or ZERO) + (r["fee"] or ZERO)
    return out


def charged(b):
    if not b.posted_on:
        return ZERO
    if b.cancelled_on is not None:
        return b.cancel_fee or ZERO
    return b.price


def figures(b, paid=None, refunded=None, credit_days=14):
    if paid is None:
        paid = paid_map([b.id]).get(b.id, ZERO)
    if refunded is None:
        refunded = refund_map([b.id]).get(b.id, ZERO)
    ch = charged(b)
    bal = ch - paid + refunded
    due = b.posted_on + datetime.timedelta(days=credit_days) if b.posted_on else None
    if b.status == "Refunded":
        st = "Refunded"
    elif not b.posted_on:
        st = "Advance received" if paid > 0 else "Not invoiced"
    elif bal < 0:
        st = "Credit due"
    elif bal == 0:
        st = "Paid"
    elif due < today():
        st = "Overdue"
    else:
        st = "Partially Paid" if paid > 0 else "Unpaid"
    outstanding = max(ZERO, bal) if b.posted_on else (max(ZERO, b.price - paid) if b.status not in ("Cancelled", "Refunded") else ZERO)
    return {"paid": paid, "refunded": refunded, "charged": ch, "balance": bal, "outstanding": outstanding, "pay_status": st, "due": due}


def booking_balance(b):
    return figures(b)["balance"]


# ---------- Posting helpers ----------

def party_name(b):
    return b.customer.name if b.customer_id else (b.agent.name if b.agent_id else "—")


def invoice_booking(b, user, on=None):
    on = on or today()
    rev, cost = SVC_ACCTS.get(b.service, SVC_ACCTS["Other"])
    b.posted_on = on
    if b.price > 0:
        post(on, b.ref, f"Invoice · {b.service} · {party_name(b)}", "Booking", [("1100", b.price, 0), (rev, 0, b.price)], user, b)
    if b.cost > 0:
        post(on, b.ref, f"Supplier cost · {b.supplier.name if b.supplier_id else 'supplier'}", "Booking", [(cost, b.cost, 0), ("2000", 0, b.cost)], user, b)


def cancel_booking(b, fee, supplier_credit, reason, user, on=None):
    on = on or today()
    fee, supplier_credit = D(fee), D(supplier_credit)
    if b.cancelled_on:
        raise ActionError("This booking is already cancelled.")
    if fee < 0 or fee > b.price:
        raise ActionError("The cancellation fee must be between 0 and the booking price.", {"fee": "Must be between 0 and the booking price."})
    if supplier_credit < 0 or supplier_credit > b.cost:
        raise ActionError("Supplier credit cannot exceed the supplier cost.", {"supplierCredit": "Cannot exceed the supplier cost."})
    rev, cost = SVC_ACCTS.get(b.service, SVC_ACCTS["Other"])
    if b.posted_on:
        reversal = b.price - fee
        if reversal > 0:
            post(on, b.ref + "-C", f"Cancellation · revenue reversed (fee kept {fee:,.0f})", "Cancellation", [("4090", reversal, 0), ("1100", 0, reversal)], user, b)
        if supplier_credit > 0:
            post(on, b.ref + "-CN", "Supplier credit note on cancellation", "Cancellation", [("2000", supplier_credit, 0), (cost, 0, supplier_credit)], user, b)
    else:
        fee, supplier_credit = ZERO, ZERO
    b.cancelled_on, b.cancel_fee, b.cancel_reason, b.supplier_credit = on, fee, reason[:300], supplier_credit
    b.status = "Cancelled"


def adjust_cost(b, new_cost, user):
    new_cost = D(new_cost)
    if b.cancelled_on:
        raise ActionError("Supplier cost cannot be changed on a cancelled booking.")
    diff = new_cost - b.cost
    if b.posted_on and diff:
        _, cost = SVC_ACCTS.get(b.service, SVC_ACCTS["Other"])
        lines = [(cost, diff, 0), ("2000", 0, diff)] if diff > 0 else [("2000", -diff, 0), (cost, 0, -diff)]
        post(today(), b.ref + "-ADJ", f"Supplier cost adjusted {b.cost:,.0f} → {new_cost:,.0f}", "Cost adjustment", lines, user, b)
    b.cost = new_cost


def supplier_ledger(s, bookings=None, payments=None):
    from .models import SupplierPayment
    bookings = bookings if bookings is not None else list(s.bookings.filter(posted_on__isnull=False))
    payments = payments if payments is not None else list(SupplierPayment.objects.filter(supplier=s))
    inv = [b for b in bookings if b.posted_on and b.cost > 0]
    inv_t = sum((b.cost for b in inv), ZERO)
    cr_t = sum((b.supplier_credit for b in inv), ZERO)
    pay_t = sum((p.amount for p in payments), ZERO)
    return {"invoiced": inv_t, "credits": cr_t, "paid": pay_t, "balance": inv_t - cr_t - pay_t}
