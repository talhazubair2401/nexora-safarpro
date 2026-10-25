"""
All write operations of Nexora SafarPro.

Each action:
  * is registered with the permission it requires (checked by the dispatcher, server-side),
  * validates its input,
  * runs inside one database transaction (all-or-nothing),
  * writes an append-only audit record,
  * posts balanced journal entries for anything that moves money.
"""
import datetime as dt
import hashlib
import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import ROLES, Employee
from accounts.permissions import has_perm
from core.audit import audit
from core.models import Branch, NotificationState, Organization, Sequence
from core.validation import PK_MOBILE, ActionError, D, Form, norm_phone
from crm.models import Communication, Customer, Document, Enquiry, Quote
from finance import ledger
from finance.ledger import ZERO, adjust_cost, cancel_booking, figures, invoice_booking, post
from finance.models import (Account, BankMatch, CashClosing, Commission, CommissionRule, Expense, JournalEntry, Payment, Period,
                            Refund, SupplierPayment)
from operations.models import (SERVICES, Agent, AgentRequest, Booking, Departure, HotelReservation, Pilgrim, Supplier, Ticket,
                               Tour, TransportArrangement, UmrahGroup, UmrahPackage, VisaApplication)

ACTIONS = {}


class Ctx:
    def __init__(self, user, files=None):
        self.user = user
        self.files = files or {}
        self.emp = getattr(user, "employee", None)
        if self.emp is None:
            raise ActionError("Your login is not linked to an employee record. Ask an administrator.", status=403)
        self.name = self.emp.name


def action(name, perm):
    def deco(fn):
        ACTIONS[name] = (fn, perm)
        return fn
    return deco


def need(ctx, perm):
    if not has_perm(ctx.user, perm):
        raise ActionError(f"Your role ({ctx.emp.role}) does not allow this action.", status=403)


def get(model, pk, label="Record"):
    try:
        return model.objects.get(pk=int(pk))
    except (model.DoesNotExist, ValueError, TypeError):
        raise ActionError(f"{label} not found. It may have been removed.", status=404)


def now_label():
    return timezone.localtime().strftime("%Y-%m-%dT%H:%M")


def tl(obj, text, ctx, field="timeline"):
    getattr(obj, field).append({"at": now_label(), "text": text, "by": ctx.name})


def money(x):
    return f"PKR {D(x):,.0f}"


def next_ref(key, prefix, width=4, start=0):
    while True:
        n = Sequence.next(key, start)
        ref = f"{prefix}{n:0{width}d}" if width else f"{prefix}{n}"
        return ref


def org():
    return Organization.get()


def branch_or_default(ctx, bid):
    if bid:
        return get(Branch, bid, "Branch")
    return ctx.emp.branch


# =============== Customers ===============

@action("customer.save", lambda d: "customer.edit" if d.get("id") else "customer.create")
def customer_save(ctx, d):
    f = Form(d)
    f.str("name", True, 150)
    phone = f.str("phone", True, 30, pattern=PK_MOBILE, pattern_msg="Use a Pakistani mobile number, e.g. 0300-5551234.")
    email = f.str("email", False, 120)
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        f.err("email", "Enter a valid email address.")
    f.choice("type", Customer.TYPES)
    f.str("country", True, 80)
    f.str("city", True, 80)
    f.str("address", False, 250)
    cnic = f.str("cnic", False, 20)
    if cnic and not re.fullmatch(r"\d{5}-?\d{7}-?\d", cnic):
        f.err("cnic", "Use the format 35202-1234567-1.")
    pno = f.str("passportNo", False, 12)
    if pno and not re.fullmatch(r"[A-Za-z]{2}\d{7}", pno):
        f.err("passportNo", "Use two letters followed by seven digits.")
    pexp = f.date("passportExpiry")
    if pexp and pexp < timezone.localdate():
        f.err("passportExpiry", "This passport has already expired.")
    f.text("notes", False, 2000)
    c = get(Customer, d["id"], "Customer") if d.get("id") else None
    if pno and not pexp and not (c and c.passport_masked):
        f.err("passportExpiry", "Add the expiry date for this passport.")
    dup = Customer.objects.filter(phone_norm=norm_phone(phone)).exclude(pk=c.pk if c else None).first() if phone else None
    if dup:
        f.err("phone", f"This number already belongs to {dup.name} ({dup.code}).")
    v = f.check()
    data = dict(name=v["name"], phone=v["phone"], phone_norm=norm_phone(v["phone"]), email=v["email"], type=v["type"], country=v["country"],
                city=v["city"], address=v["address"], notes=v["notes"])
    if cnic:
        data["cnic_masked"] = "•••••-•••••••-" + cnic[-1]
    if pno:
        data["passport_masked"] = "••••" + pno[-3:].upper()
    if pexp:
        data["passport_expiry"] = pexp
    if c:
        changed = [k for k, val in data.items() if k != "phone_norm" and getattr(c, k) != val]
        if not changed:
            return {"message": "No changes to save."}
        prev = "; ".join(f"{k}: {getattr(c, k) or '—'}" for k in changed)
        for k, val in data.items():
            setattr(c, k, val)
        c.save()
        audit(ctx.user, "Customer information updated", "Customers", c.code, prev, "; ".join(f"{k}: {data[k] or '—'}" for k in changed), severity="Low")
        return {"id": str(c.pk), "message": "Customer updated."}
    code = next_ref("customer", "SP-CU-", 0, 1000)
    c = Customer.objects.create(code=code, branch=branch_or_default(ctx, d.get("branch")), **data)
    audit(ctx.user, "Customer created", "Customers", c.code, next=c.name)
    return {"id": str(c.pk), "message": "Customer created successfully."}


@action("customer.status", "customer.edit")
def customer_status(ctx, d):
    c = get(Customer, d.get("id"), "Customer")
    prev = c.status
    c.status = "Inactive" if c.status == "Active" else "Active"
    c.save(update_fields=["status"])
    audit(ctx.user, "Customer status changed", "Customers", c.code, prev, c.status)
    return {"message": f"{c.name} is now {c.status.lower()}."}


@action("customer.import", "customer.create")
def customer_import(ctx, d):
    rows = d.get("rows") or []
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ActionError("Paste up to 2,000 rows at a time.")
    added, skipped, bad = 0, [], 0
    seen = set()
    for r in rows:
        name, phone = (r.get("name") or "").strip()[:150], (r.get("phone") or "").strip()[:30]
        if not name or not re.fullmatch(PK_MOBILE, phone):
            bad += 1
            continue
        pn = norm_phone(phone)
        ex = Customer.objects.filter(phone_norm=pn).first()
        if ex or pn in seen:
            skipped.append(ex.name if ex else name)
            continue
        seen.add(pn)
        typ = r.get("type") if r.get("type") in Customer.TYPES else "Individual"
        Customer.objects.create(code=next_ref("customer", "SP-CU-", 0, 1000), name=name, phone=phone, phone_norm=pn, email=(r.get("email") or "")[:120],
                                type=typ, city=(r.get("city") or ctx.emp.branch.city)[:80], branch=ctx.emp.branch, notes="Imported")
        added += 1
    if added:
        audit(ctx.user, "Customers imported", "Customers", f"{added} records", next=f"{added} added, {len(skipped)} duplicates skipped, {bad} invalid")
    return {"added": added, "skipped": skipped[:20], "bad": bad,
            "message": f"{added} customer{'s' if added != 1 else ''} imported" + (f", {len(skipped)} duplicate(s) skipped" if skipped else "") + (f", {bad} invalid row(s)" if bad else "") + "."}


@action("comm.add", "customer.edit")
def comm_add(ctx, d):
    c = get(Customer, d.get("customerId"), "Customer")
    f = Form(d)
    ch = f.choice("channel", ["Note", "WhatsApp", "SMS", "Email", "Phone"])
    text = f.text("text", True, 2000)
    f.check()
    Communication.objects.create(customer=c, channel=ch, direction="Internal" if ch == "Note" else "Outgoing", text=text, by=ctx.name)
    audit(ctx.user, "Internal note added" if ch == "Note" else "Communication logged", "Customers", c.code, next=ch, severity="Low")
    return {"message": "Note saved." if ch == "Note" else f"{ch} message logged. SafarPro does not send messages itself."}


# =============== Enquiries & quotes ===============

@action("enquiry.save", lambda d: "enquiry.edit" if d.get("id") else "enquiry.create")
def enquiry_save(ctx, d):
    f = Form(d)
    who = f.choice("who", ["existing", "lead"])
    cust = None
    if who == "existing":
        f.str("customerId", True)
        if d.get("customerId"):
            cust = get(Customer, d["customerId"], "Customer")
    else:
        f.str("lead", True, 150)
        f.str("phone", True, 30, pattern=PK_MOBILE, pattern_msg="Use a Pakistani mobile number.")
    f.choice("service", SERVICES)
    f.str("dest", True, 150)
    td = f.date("travelDate", True)
    f.money("value", True)
    f.str("emp", True)
    f.choice("source", ["WhatsApp", "Walk-in", "Phone", "Facebook", "Email", "Referral", "Website"])
    f.date("nextFollow", True)
    e = get(Enquiry, d["id"], "Enquiry") if d.get("id") else None
    if td and not e and td < timezone.localdate():
        f.err("travelDate", "Travel date is in the past.")
    v = f.check()
    emp = get(Employee, v["emp"], "Employee")
    data = dict(customer=cust, lead=v.get("lead", "") if who == "lead" else "", phone=v.get("phone") if who == "lead" else cust.phone,
                service=v["service"], dest=v["dest"], travel_date=v["travelDate"], value=v["value"], employee=emp, source=v["source"], next_follow=v["nextFollow"])
    if e:
        for k, val in data.items():
            setattr(e, k, val)
        tl(e, "Enquiry details updated", ctx, "history")
        e.save()
        audit(ctx.user, "Enquiry updated", "Enquiries", e.ref)
        return {"id": str(e.pk), "message": "Enquiry updated."}
    e = Enquiry(ref=next_ref("enquiry", "SP-EQ-"), branch=cust.branch if cust else ctx.emp.branch, history=[], **data)
    tl(e, "Enquiry received via " + v["source"], ctx, "history")
    e.save()
    audit(ctx.user, "Enquiry created", "Enquiries", e.ref, next=f"{cust.name if cust else e.lead} · {e.service}")
    return {"id": str(e.pk), "message": "Enquiry created."}


@action("enquiry.stage", "enquiry.edit")
def enquiry_stage(ctx, d):
    e = get(Enquiry, d.get("id"), "Enquiry")
    stage = d.get("stage")
    if stage not in Enquiry.STAGES or stage == "Converted":
        raise ActionError("Choose a valid stage. Use “Convert to booking” to convert.")
    if e.stage == "Converted":
        raise ActionError("This enquiry is already converted to a booking. Its history is preserved.")
    prev = e.stage
    if stage == "Lost":
        reason = (d.get("reason") or "").strip()
        if not reason:
            raise ActionError("Give a reason for marking the enquiry as lost.", {"reason": "Required."})
        e.lost_reason = reason[:250]
    e.stage = stage
    tl(e, f"Moved from {prev} to {stage}" + (f" — {e.lost_reason}" if stage == "Lost" else ""), ctx, "history")
    e.save()
    audit(ctx.user, "Enquiry stage changed", "Enquiries", e.ref, prev, stage, d.get("reason", ""))
    return {"message": f"{e.ref} moved to {stage}."}


@action("enquiry.followup", "enquiry.edit")
def enquiry_followup(ctx, d):
    e = get(Enquiry, d.get("id"), "Enquiry")
    f = Form(d)
    date = f.date("date", True)
    note = f.text("note", True, 500)
    if date and date < timezone.localdate():
        f.err("date", "Choose today or a future date.")
    f.check()
    e.next_follow = date
    if e.stage == "New":
        e.stage = "Contacted"
    tl(e, f"Follow-up set for {date:%d %b %Y} — {note}", ctx, "history")
    e.save()
    audit(ctx.user, "Follow-up added", "Enquiries", e.ref, next=str(date))
    return {"message": "Follow-up saved."}


@action("enquiry.assign", "enquiry.edit")
def enquiry_assign(ctx, d):
    e = get(Enquiry, d.get("id"), "Enquiry")
    emp = get(Employee, d.get("emp"), "Employee")
    prev = e.employee.name
    e.employee = emp
    tl(e, f"Assigned to {emp.name}", ctx, "history")
    e.save()
    audit(ctx.user, "Enquiry reassigned", "Enquiries", e.ref, prev, emp.name)
    return {"message": f"Assigned to {emp.name}."}


@action("enquiry.ensureCustomer", "customer.create")
def enquiry_ensure_customer(ctx, d):
    """Before converting a lead, reuse an existing customer with the same phone or create one."""
    e = get(Enquiry, d.get("id"), "Enquiry")
    if e.customer_id:
        return {"customerId": str(e.customer_id)}
    ex = Customer.objects.filter(phone_norm=norm_phone(e.phone)).first()
    if not ex:
        ex = Customer.objects.create(code=next_ref("customer", "SP-CU-", 0, 1000), name=e.lead, phone=e.phone, phone_norm=norm_phone(e.phone),
                                     city=e.branch.city, branch=e.branch, notes=f"Created from enquiry {e.ref}")
        audit(ctx.user, "Customer created", "Customers", ex.code, next=f"{ex.name} (from enquiry {e.ref})")
    e.customer = ex
    e.save(update_fields=["customer"])
    return {"customerId": str(ex.pk)}


@action("quote.create", "enquiry.create")
def quote_create(ctx, d):
    f = Form(d)
    to = f.str("to", True, 150)
    title = f.str("title", True, 200)
    valid = f.date("valid", True)
    terms = f.str("terms", False, 300)
    items = []
    for i, line in enumerate((d.get("items") or "").split("\n")):
        if not line.strip():
            continue
        m = re.fullmatch(r"(.+)\|\s*(\d+)\s*", line)
        if not m:
            f.err("items", f"Line {i + 1} needs “| amount” at the end.")
            break
        items.append({"d": m.group(1).strip()[:200], "a": int(m.group(2))})
    if not items:
        f.err("items", "Add at least one line item.")
    if valid and valid < timezone.localdate():
        f.err("valid", "Choose a future date.")
    f.check()
    e = get(Enquiry, d["enquiryId"], "Enquiry") if d.get("enquiryId") else None
    q = Quote.objects.create(ref=next_ref("quote", "SP-QT-"), to=to, title=title, items=items, total=sum(i["a"] for i in items), valid_until=valid, terms=terms, enquiry=e)
    if e and e.stage in ("New", "Contacted", "Follow-up Required"):
        e.stage = "Quotation Sent"
        tl(e, f"Quotation {q.ref} created · {money(q.total)}", ctx, "history")
        e.save()
    audit(ctx.user, "Quotation created", "Enquiries", q.ref, next=money(q.total))
    return {"id": str(q.pk), "ref": q.ref, "total": int(q.total)}


# =============== Bookings ===============

def create_commissions(b, ctx_name="System"):
    kind = "Sub-agent commission" if b.agent_id else "Employee incentive"
    rule = CommissionRule.objects.filter(kind=kind, service=b.service).first()
    if not rule or rule.rate is None:
        return
    rate = rule.rate
    if rule.basis == "% of margin":
        amt = (b.price - b.cost) * rate / 100
    elif rule.basis == "% of selling price":
        amt = b.price * rate / 100
    elif rule.basis == "Fixed per passenger":
        amt = rate * b.pax
    else:
        amt = rate
    amt = D(amt)
    if amt <= 0:
        return
    basis = f"{rule.basis} ({rate.normalize()}%)" if rule.basis.startswith("%") else f"{rule.basis} (PKR {rate:,.0f})"
    Commission.objects.create(ref=next_ref("commission", "SP-CM-"), kind=kind, party=b.agent.name if b.agent_id else b.employee.name,
                              agent=b.agent if b.agent_id else None, employee=None if b.agent_id else b.employee, booking=b,
                              basis=basis, amount=amt, status="Pending", date=b.posted_on or timezone.localdate())


def confirm_and_invoice(b, ctx, on=None):
    if b.departure_id:
        dep = b.departure
        if booked_seats(dep, exclude=b.pk) + b.pax > dep.capacity and not getattr(b, "_override", False):
            raise ActionError("This departure is full. Free seats or use an authorised override.")
    invoice_booking(b, ctx.user, on)
    if b.status in ("Draft", "Pending"):
        b.status = "Confirmed"
    tl(b, "Booking confirmed and invoiced", ctx)
    b.save()
    create_commissions(b)


def booked_seats(dep, exclude=None):
    qs = dep.bookings.exclude(status__in=["Cancelled", "Refunded", "Draft"])
    if exclude:
        qs = qs.exclude(pk=exclude)
    return sum(qs.values_list("pax", flat=True))


def new_booking(ctx, **kw):
    status = kw.pop("status")
    on = kw.pop("posted_on", None)
    override = kw.pop("override", False)
    b = Booking(ref=next_ref("booking", org().booking_prefix, 0, 1000), timeline=[], created=kw.pop("created", timezone.localdate()), **kw)
    if not b.branch_id:
        b.branch = b.customer.branch if b.customer_id else (b.agent.branch if b.agent_id else ctx.emp.branch)
    b.status = status
    b._override = override
    tl(b, "Booking created", ctx)
    b.save()
    if status in ("Confirmed", "Completed"):
        confirm_and_invoice(b, ctx, on)
        if status == "Completed":
            b.status = "Completed"
            b.save(update_fields=["status"])
    return b


@action("booking.create", "booking.create")
def booking_create(ctx, d):
    f = Form(d)
    f.str("customerId", True)
    service = f.choice("service", SERVICES)
    dep = None
    if service == "Tour":
        f.str("depId", True)
        if d.get("depId"):
            dep = get(Departure, d["depId"], "Departure")
    f.str("destination", True, 200)
    f.date("travelDate", True)
    pax = f.int("pax", True, 1, 500)
    f.text("passengers", False, 5000)
    price = f.money("price", True)
    cost = f.money("cost")
    f.str("supplierId")
    status = f.choice("status", ["Draft", "Pending", "Confirmed"])
    f.str("emp", True)
    override = f.bool("override")
    f.text("notes", False, 3000)
    if cost > 0 and not d.get("supplierId"):
        f.err("supplierId", "Choose the supplier this cost is owed to.")
    if dep and pax:
        left = dep.capacity - booked_seats(dep)
        if pax > left:
            if not override:
                f.err("pax", f"Only {left} seats left on this departure.")
            elif ctx.emp.role not in ("Administrator", "Owner"):
                f.err("override", "Only an Administrator can authorise an overbooking.")
    v = f.check()
    cust = get(Customer, v["customerId"], "Customer")
    if cust.status != "Active":
        raise ActionError("This customer is inactive. Reactivate them first.", {"customerId": "Customer is inactive."})
    names = [x.strip()[:150] for x in v["passengers"].split("\n") if x.strip()]
    kw = dict(customer=cust, service=service, destination=v["destination"], travel_date=v["travelDate"], pax=pax, passengers=names or [cust.name],
              price=price, cost=cost, supplier=get(Supplier, v["supplierId"], "Supplier") if v["supplierId"] else None,
              employee=get(Employee, v["emp"], "Employee"), notes=v["notes"], departure=dep)
    if d.get("enquiryId"):
        kw["enquiry"] = get(Enquiry, d["enquiryId"], "Enquiry")
    b = new_booking(ctx, status=status, override=override and bool(dep), **kw)
    if override and dep:
        tl(b, "Capacity override authorised by Administrator", ctx)
        b.save(update_fields=["timeline"])
    if kw.get("enquiry"):
        e = kw["enquiry"]
        e.stage, e.booking, e.customer = "Converted", b, cust
        tl(e, f"Converted to booking {b.ref}", ctx, "history")
        e.save()
        tl(b, f"Created from enquiry {e.ref}", ctx)
        b.save(update_fields=["timeline"])
    audit(ctx.user, "Booking created", "Bookings", b.ref, next=f"{b.status} · {money(b.price)}", reason="Capacity override" if override else "",
          severity="High" if override and dep else "Info")
    return {"id": str(b.pk), "ref": b.ref, "message": f"Booking {b.ref} created."}


@action("booking.confirm", "booking.edit")
def booking_confirm(ctx, d):
    b = get(Booking, d.get("id"), "Booking")
    if b.status not in ("Draft", "Pending") or b.posted_on:
        raise ActionError("Only draft or pending bookings can be confirmed.")
    prev = b.status
    confirm_and_invoice(b, ctx)
    if hasattr(b, "visa"):
        pass
    audit(ctx.user, "Booking confirmed", "Bookings", b.ref, prev, "Confirmed")
    return {"message": f"{b.ref} confirmed and invoiced."}


@action("booking.complete", "booking.edit")
def booking_complete(ctx, d):
    b = get(Booking, d.get("id"), "Booking")
    if b.status != "Confirmed":
        raise ActionError("Only confirmed bookings can be marked completed.")
    b.status = "Completed"
    tl(b, "Marked completed (travel finished)", ctx)
    b.save()
    audit(ctx.user, "Booking completed", "Bookings", b.ref, "Confirmed", "Completed")
    bal = figures(b, credit_days=org().credit_days)["balance"]
    return {"message": "Booking marked completed." + (f" Note: {money(bal)} is still outstanding." if bal > 0 else "")}


def _reverse_open_commissions(b, reason):
    for c in b.commissions.filter(status__in=["Pending", "Approved"]):
        c.status, c.reverse_reason = "Reversed", reason[:300]
        c.save()


@action("booking.cancel", "booking.edit")
def booking_cancel(ctx, d):
    b = get(Booking, d.get("id"), "Booking")
    if b.status in ("Cancelled", "Refunded", "Completed"):
        raise ActionError(f"A {b.status.lower()} booking cannot be cancelled.")
    f = Form(d)
    fee = f.money("fee", False, max_value=b.price)
    sc = f.money("supplierCredit", False, max_value=b.cost)
    reason = f.text("reason", True, 300)
    f.check()
    prev = b.status
    cancel_booking(b, fee, sc, reason, ctx.user)
    b.tickets.filter(status="Issued").update(status="Cancelled")
    tl(b, f"Booking cancelled" + (f" · fee {money(b.cancel_fee)}" if b.posted_on else "") + (f" · supplier credit {money(sc)}" if sc else "") + f" — {reason}", ctx)
    b.save()
    _reverse_open_commissions(b, "Booking cancelled")
    audit(ctx.user, "Booking cancelled", "Bookings", b.ref, prev, "Cancelled", reason, "Medium")
    bal = figures(b)["balance"]
    return {"message": f"{b.ref} cancelled." + (f" A credit of {money(-bal)} is due — create a refund to pay it out." if bal < 0 else "")}


@action("booking.notes", "booking.edit")
def booking_notes(ctx, d):
    b = get(Booking, d.get("id"), "Booking")
    f = Form(d)
    notes = f.text("notes", False, 5000)
    pas = f.text("passengers", False, 5000)
    f.check()
    b.notes = notes
    b.passengers = [x.strip()[:150] for x in pas.split("\n") if x.strip()]
    tl(b, "Notes / passengers updated", ctx)
    b.save()
    audit(ctx.user, "Booking details updated", "Bookings", b.ref, severity="Low")
    return {"message": "Booking updated."}


@action("booking.cost", "booking.approve")
def booking_cost(ctx, d):
    b = get(Booking, d.get("id"), "Booking")
    f = Form(d)
    new = f.money("cost", True)
    reason = f.text("reason", True, 300)
    if new < b.supplier_credit:
        f.err("cost", "Cannot be lower than the supplier credit already received.")
    f.check()
    prev = b.cost
    if prev == new:
        return {"message": "Cost unchanged."}
    adjust_cost(b, new, ctx.user)
    tl(b, f"Supplier cost changed {money(prev)} → {money(new)} — {reason}", ctx)
    b.save()
    audit(ctx.user, "Supplier cost changed", "Bookings", b.ref, money(prev), money(new), reason, "High")
    return {"message": "Supplier cost updated. An adjustment entry was posted." if b.posted_on else "Supplier cost updated."}


# =============== Payments ===============

def record_payment(ctx, b, amount, date, method, tx_ref="", notes="", by=None):
    o = org()
    fig = figures(b, credit_days=o.credit_days)
    if b.status in ("Cancelled", "Refunded") and fig["balance"] <= 0:
        raise ActionError("This booking is cancelled and has nothing outstanding.")
    if b.status == "Draft":
        raise ActionError("Draft bookings cannot take payments. Mark it pending or confirmed first.")
    outstanding = fig["outstanding"]
    if amount > outstanding and not o.allow_overpayment:
        raise ActionError("Amount exceeds the outstanding balance.", {"amount": f"Amount exceeds the outstanding balance of {money(outstanding)}. Overpayments are turned off in Settings → Financial."})
    if method not in o.payment_methods:
        raise ActionError("Choose a payment method.", {"method": "Not an allowed payment method."})
    if method != "Cash" and not tx_ref:
        raise ActionError("Reference required.", {"txRef": "Required for non-cash payments."})
    if tx_ref and Payment.objects.filter(tx_ref__iexact=tx_ref, status="Posted").exists():
        raise ActionError("Possible duplicate payment.", {"txRef": "This reference is already recorded on another receipt — possible duplicate."})
    acct = ledger.account_for_method(method, b.branch)
    prev = fig["balance"] if b.posted_on else b.price - fig["paid"]
    ref = next_ref("receipt", o.receipt_prefix, 6, 100)
    p = Payment.objects.create(ref=ref, booking=b, date=date, method=method, account=acct, amount=amount, tx_ref=tx_ref, received_by=by or ctx.emp,
                               branch=b.branch, notes=notes, prev_balance=prev, new_balance=prev - amount)
    post(date, ref, f"Receipt · {method} · {ledger.party_name(b)}", "Receipt", [(acct.code, amount, 0), ("1100", 0, amount)], ctx.user, b)
    tl(b, f"Payment {ref} received · {money(amount)} ({method})", ctx)
    b.save(update_fields=["timeline"])
    return p


@action("payment.create", "payment.create")
def payment_create(ctx, d):
    f = Form(d)
    f.str("bookingId", True)
    date = f.date("date", True)
    f.str("method", True)
    amount = f.money("amount", True, Decimal("1"))
    tx = f.str("txRef", False, 60)
    notes = f.str("notes", False, 300)
    v = f.check()
    if date:
        ledger.assert_open(date)
    b = get(Booking, v["bookingId"], "Booking")
    p = record_payment(ctx, b, amount, date, v["method"], tx, notes)
    audit(ctx.user, "Payment created", "Payments", p.ref, next=f"{money(p.amount)} · {p.method} · {ledger.party_name(b)}")
    return {"id": str(p.pk), "ref": p.ref, "message": f"Payment recorded. Receipt {p.ref} generated."}


@action("payment.reverse", "payment.reverse")
def payment_reverse(ctx, d):
    p = get(Payment, d.get("id"), "Payment")
    reason = (d.get("reason") or "").strip()
    if not reason:
        raise ActionError("A reason is required.", {"reason": "Required."})
    if p.status != "Posted":
        raise ActionError("This receipt is already reversed.")
    if p.booking.refunds.exclude(status__in=["Completed", "Rejected"]).exists():
        raise ActionError("This booking has an open refund. Finish or reject the refund before reversing receipts.")
    t = timezone.localdate()
    post(t, p.ref + "-R", f"Receipt reversed · {reason[:120]}", "Reversal", [("1100", p.amount, 0), (p.account.code, 0, p.amount)], ctx.user, p.booking)
    p.status, p.reversed_on, p.reverse_reason = "Reversed", t, reason[:300]
    p.save()
    tl(p.booking, f"Receipt {p.ref} reversed — {reason}", ctx)
    p.booking.save(update_fields=["timeline"])
    audit(ctx.user, "Payment reversed", "Payments", p.ref, "Posted", "Reversed", reason, "High")
    return {"message": f"Receipt {p.ref} reversed."}


# =============== Air tickets ===============

@action("ticket.create", "ticket.create")
def ticket_create(ctx, d):
    f = Form(d)
    f.str("customerId", True)
    passenger = f.str("passenger", True, 150)
    airline = f.str("airline", True, 60)
    orig = f.str("from", True, 3, pattern=r"[A-Za-z]{3}", pattern_msg="Use a 3-letter airport code.").upper()
    dest = f.str("to", True, 3, pattern=r"[A-Za-z]{3}", pattern_msg="Use a 3-letter airport code.").upper()
    if orig and orig == dest:
        f.err("to", "Destination must differ from origin.")
    dep = f.date("dep", True)
    ret = f.date("ret")
    if dep and dep < timezone.localdate():
        f.err("dep", "Departure is in the past.")
    if ret and dep and ret < dep:
        f.err("ret", "Return must be after departure.")
    pnr = f.str("pnr", True, 6, pattern=r"[A-Za-z0-9]{6}", pattern_msg="PNR must be 6 letters or digits.").upper()
    no = f.str("no", True, 14, pattern=r"\d{3}-?\d{10}", pattern_msg="Use the 13-digit format 176-1234567890.")
    no = (no[:3] + "-" + no[3:]) if no and "-" not in no else no
    if no and Ticket.objects.filter(number=no).exists():
        f.err("no", "This ticket number already exists.")
    f.str("supplierId", True)
    cost = f.money("cost", True)
    sell = f.money("sell", True)
    comm = f.money("commission")
    fee = f.money("fee")
    status = f.choice("status", ["Issued", "On Hold"])
    f.str("emp", True)
    collect = f.money("collect")
    notes = f.text("notes", False, 1000)
    if comm > cost:
        f.err("commission", "Commission cannot exceed the supplier cost.")
    if collect > sell + fee:
        f.err("collect", "Cannot collect more than the ticket total.")
    v = f.check()
    cust = get(Customer, v["customerId"], "Customer")
    sup = get(Supplier, v["supplierId"], "Supplier")
    emp = get(Employee, v["emp"], "Employee")
    b = new_booking(ctx, status="Confirmed" if status == "Issued" else "Pending", customer=cust, service="Air Ticket",
                    destination=f"{orig} → {dest}" + (f" → {orig}" if ret else ""), travel_date=dep, return_date=ret, pax=1, passengers=[passenger],
                    price=sell + fee, cost=cost - comm, supplier=sup, employee=emp, notes=notes, airline=airline)
    t = Ticket.objects.create(booking=b, passenger=passenger, airline=airline, number=no, pnr=pnr, origin=orig, dest=dest, dep=dep, ret=ret,
                              supplier=sup, cost=cost, sell=sell, fee=fee, commission=comm, status=status, employee=emp)
    if comm > 0:
        Commission.objects.create(ref=next_ref("commission", "SP-CM-"), kind="Supplier commission (earned)", party=sup.name, supplier=sup, booking=b,
                                  basis="Netted in ticket cost", amount=comm, status="Netted in cost", date=timezone.localdate())
    audit(ctx.user, "Ticket recorded", "Air Tickets", t.number, next=f"{airline} · {orig}–{dest} · {status}")
    if collect > 0:
        p = record_payment(ctx, b, collect, timezone.localdate(), "Cash", "", "Collected at ticketing")
        audit(ctx.user, "Payment created", "Payments", p.ref, next=money(collect))
    return {"id": str(b.pk), "message": f"Ticket {t.number} saved on booking {b.ref}."}


@action("ticket.void", "ticket.edit")
def ticket_void(ctx, d):
    t = get(Ticket, d.get("id"), "Ticket")
    reason = (d.get("reason") or "").strip()
    if not reason:
        raise ActionError("A reason is required.", {"reason": "Required."})
    if t.status != "Issued":
        raise ActionError("Only issued tickets can be voided.")
    if t.dep <= timezone.localdate():
        raise ActionError("A ticket can only be voided before departure. Use a refund request instead.")
    b = t.booking
    if b.refunds.exclude(status__in=["Completed", "Rejected"]).exists():
        raise ActionError("This booking has an open refund request.")
    tickets = b.tickets.filter(status="Issued")
    cancel_booking(b, 0, b.cost, "Ticket voided — " + reason, ctx.user)
    tickets.update(status="Void")
    tl(b, f"Tickets voided — {reason}", ctx)
    b.save()
    _reverse_open_commissions(b, "Ticket voided")
    b.commissions.filter(kind="Supplier commission (earned)").update(status="Reversed", reverse_reason="Ticket voided")
    audit(ctx.user, "Ticket voided", "Air Tickets", t.number, "Issued", "Void", reason, "High")
    bal = figures(b)["balance"]
    return {"message": "Tickets voided and accounting reversed." + (f" {money(-bal)} paid by the customer must be refunded." if bal < 0 else "")}


# =============== Visa ===============

@action("visa.create", "visa.create")
def visa_create(ctx, d):
    f = Form(d)
    f.str("customerId", True)
    country = f.str("country", True, 80)
    vtype = f.str("type", True, 80)
    travel = f.date("travel", True)
    emb = f.money("emb", True)
    svc = f.money("svc", True)
    f.str("officer", True)
    status = f.choice("status", ["New Enquiry", "Documents Pending"])
    notes = f.text("notes", False, 2000)
    if travel and travel < timezone.localdate():
        f.err("travel", "Choose a future date.")
    v = f.check()
    c = get(Customer, v["customerId"], "Customer")
    officer = get(Employee, v["officer"], "Employee")
    vs = get(Supplier, d["supplierId"], "Supplier") if d.get("supplierId") else Supplier.objects.filter(category="Visa Service Provider").first()
    b = new_booking(ctx, status="Pending", customer=c, service="Visa", destination=country, travel_date=travel, pax=1, passengers=[c.name],
                    price=emb + svc, cost=emb, supplier=vs, employee=officer)
    if emb > 0 and not vs:
        b.cost = ZERO  # no supplier recorded: embassy fee treated as pass-through paid directly by customer
        b.save(update_fields=["cost"])
    docs = [{"name": n, "status": "Received" if (i == 0 and c.passport_masked) else "Missing"} for i, n in enumerate(org().visa_docs)]
    va = VisaApplication.objects.create(ref=next_ref("visa", "SP-VA-", 0, 2600), booking=b, country=country, type=vtype, status=status, embassy_fee=emb,
                                        service_fee=svc, officer=officer, docs=docs, timeline=[{"at": now_label(), "text": "Application opened", "by": ctx.name}], notes=notes)
    audit(ctx.user, "Visa application created", "Visa", va.ref, next=f"{country} · {status}")
    return {"id": str(va.pk), "message": f"Visa application {va.ref} created."}


@action("visa.status", "visa.edit")
def visa_status(ctx, d):
    va = get(VisaApplication, d.get("id"), "Visa application")
    status = d.get("status")
    if status not in VisaApplication.STAGES:
        raise ActionError("Choose a valid stage.")
    if status == va.status:
        return {"message": "No change."}
    si = VisaApplication.STAGES.index(status)
    if si >= 4 and org().visa_docs_required and any(x["status"] == "Missing" for x in va.docs):
        raise ActionError("Some required documents are still missing. Mark them received or verified before submitting.")
    prev = va.status
    va.status = status
    va.timeline.insert(0, {"at": now_label(), "text": f"Status changed: {prev} → {status}", "by": ctx.name})
    if status == "Submitted" and not va.submitted:
        va.submitted = timezone.localdate()
        va.expected = va.submitted + dt.timedelta(days=14)
    va.save()
    b = va.booking
    invoiced = False
    if si >= 4 and not b.posted_on and b.status in ("Pending", "Draft"):
        tl(b, "Visa submitted — fees invoiced", ctx)
        confirm_and_invoice(b, ctx)
        invoiced = True
    if status == "Closed" and b.status == "Confirmed":
        b.status = "Completed"
        b.save(update_fields=["status"])
    audit(ctx.user, "Visa status updated", "Visa", va.ref, prev, status, severity="Medium" if status in ("Approved", "Rejected") else "Info")
    return {"message": f"{va.ref} moved to {status}." + (" Fees have been invoiced." if invoiced else "")}


@action("visa.doc", "visa.edit")
def visa_doc(ctx, d):
    va = get(VisaApplication, d.get("id"), "Visa application")
    try:
        doc = va.docs[int(d.get("i"))]
    except (ValueError, IndexError, TypeError):
        raise ActionError("Document not found.")
    order = ["Missing", "Received", "Verified"]
    prev = doc["status"]
    doc["status"] = order[(order.index(prev) + 1) % 3]
    va.timeline.insert(0, {"at": now_label(), "text": f"{doc['name']}: {prev} → {doc['status']}", "by": ctx.name})
    va.save()
    audit(ctx.user, "Visa document updated", "Visa", va.ref, f"{doc['name']}: {prev}", doc["status"], severity="Low")
    return {}


@action("visa.reminder", "visa.edit")
def visa_reminder(ctx, d):
    va = get(VisaApplication, d.get("id"), "Visa application")
    if d.get("toggle") is not None:
        try:
            r = va.reminders[int(d["toggle"])]
        except (ValueError, IndexError):
            raise ActionError("Reminder not found.")
        r["done"] = not r.get("done")
    else:
        f = Form(d)
        date = f.date("date", True)
        text = f.str("text", True, 200)
        f.check()
        va.reminders.append({"date": date.isoformat(), "text": text, "done": False})
        audit(ctx.user, "Visa reminder added", "Visa", va.ref, next=str(date), severity="Low")
    va.save()
    return {"message": "Reminder saved."}


@action("visa.notes", "visa.edit")
def visa_notes(ctx, d):
    va = get(VisaApplication, d.get("id"), "Visa application")
    va.notes = (d.get("notes") or "")[:4000]
    va.save(update_fields=["notes"])
    audit(ctx.user, "Visa notes updated", "Visa", va.ref, severity="Low")
    return {"message": "Notes saved."}


# =============== Umrah ===============

@action("umrah.package", "umrah.create")
def umrah_package(ctx, d):
    f = Form(d)
    name = f.str("name", True, 150)
    days = f.int("days", True, 1, 60)
    mk = f.str("makkah", True, 150)
    md = f.str("madinah", True, 150)
    tr = f.str("transport", False, 150)
    room = f.str("room", False, 60)
    fl = f.str("flight", False, 150)
    cost = f.money("cost", True)
    sell = f.money("sell", True)
    cap = f.int("capacity", True, 1, 500)
    inc = f.text("inc", False)
    exc = f.text("exc", False)
    f.check()
    p = UmrahPackage.objects.create(name=name, days=days, makkah=mk, madinah=md, transport=tr, room=room, flight=fl, cost=cost, sell=sell, capacity=cap,
                                    inclusions=[x.strip() for x in inc.split("\n") if x.strip()], exclusions=[x.strip() for x in exc.split("\n") if x.strip()])
    audit(ctx.user, "Umrah package created", "Umrah", p.name, next=money(sell))
    return {"id": str(p.pk), "message": "Package created."}


@action("umrah.book", "umrah.create")
def umrah_book(ctx, d):
    f = Form(d)
    f.str("pkgId", True)
    gid = f.str("groupId", True)
    if gid == "new":
        f.str("gname", True, 150)
        gdep = f.date("gdep", True)
        if gdep and gdep < timezone.localdate():
            f.err("gdep", "Choose a future date.")
    f.str("customerId", True)
    f.str("emp", True)
    names = [x.strip()[:150] for x in (d.get("pilgrims") or "").split("\n") if x.strip()]
    if not names:
        f.err("pilgrims", "Enter at least one pilgrim name.")
    v = f.check()
    p = get(UmrahPackage, v["pkgId"], "Package")
    if gid == "new":
        n = Sequence.next("umrahgroup")
        g = UmrahGroup.objects.create(ref=f"UG-{v['gdep']:%y%m}-{n:03d}", name=v["gname"], package=p, departure=v["gdep"], return_date=v["gdep"] + dt.timedelta(days=p.days))
    else:
        g = get(UmrahGroup, gid, "Group")
    if g.package_id != p.pk:
        raise ActionError("This group uses a different package.", {"groupId": "This group uses a different package."})
    used = g.pilgrims.count()
    if used + len(names) > p.capacity:
        raise ActionError("Group is full.", {"pilgrims": f"Only {p.capacity - used} places left in this group."})
    sup = Supplier.objects.filter(category="Umrah Package Supplier").first()
    b = new_booking(ctx, status="Pending", customer=get(Customer, v["customerId"], "Customer"), service="Umrah", destination="Makkah & Madinah",
                    travel_date=g.departure, return_date=g.return_date, pax=len(names), passengers=names, price=p.sell * len(names),
                    cost=p.cost * len(names) if sup else ZERO, supplier=sup, employee=get(Employee, v["emp"], "Employee"), group=g, notes=f"{p.name} · {g.ref}")
    Pilgrim.objects.bulk_create([Pilgrim(group=g, booking=b, name=n) for n in names])
    audit(ctx.user, "Umrah booking created", "Umrah", b.ref, next=f"{len(names)} pilgrims · {g.ref}")
    return {"groupId": str(g.pk), "message": f"{len(names)} pilgrim(s) added to {g.ref}. Booking {b.ref} is pending until you confirm it."}


@action("pilgrim.update", "umrah.edit")
def pilgrim_update(ctx, d):
    pg = get(Pilgrim, d.get("id"), "Pilgrim")
    f = Form(d)
    name = f.str("name", True, 150)
    ps = f.choice("passport", ["Valid", "Expiring", "Missing"])
    vs = f.choice("visa", ["Pending documents", "Applied", "Approved", "Rejected"])
    room = f.str("room", False, 80)
    pay = f.choice("payment", ["Paid", "Partial", "Pending"])
    em = f.str("emergency", False, 120)
    sp = f.str("special", False, 200)
    f.check()
    changes = [f"{k}: {a} → {b}" for k, a, b in [("passport", pg.passport_status, ps), ("visa", pg.visa_status, vs), ("room", pg.room, room), ("payment", pg.payment_status, pay)] if a != b]
    pg.name, pg.passport_status, pg.visa_status, pg.room, pg.payment_status, pg.emergency, pg.special = name, ps, vs, room, pay, em, sp
    pg.save()
    audit(ctx.user, "Pilgrim updated", "Umrah", pg.name, next="; ".join(changes) or "details", severity="Low")
    return {"message": "Pilgrim record updated."}


@action("group.update", "umrah.edit")
def group_update(ctx, d):
    g = get(UmrahGroup, d.get("id"), "Group")
    f = Form(d)
    for k in ("flight", "retFlight", "leader", "status"):
        f.str(k, True, 150)
    v = f.check()
    g.flight, g.return_flight, g.leader, g.status = v["flight"], v["retFlight"], v["leader"], v["status"]
    g.save()
    audit(ctx.user, "Group details updated", "Umrah", g.ref, severity="Low")
    return {"message": "Group updated."}


# =============== Tours ===============

@action("tour.save", "umrah.create")
def tour_save(ctx, d):
    f = Form(d)
    name = f.str("name", True, 150)
    dest = f.str("dest", True, 120)
    region = f.choice("region", ["Domestic", "International"])
    days = f.int("days", True, 1, 60)
    price = f.money("price", True)
    cost = f.money("cost", True)
    f.str("sup")
    tr = f.str("transport", False, 150)
    hotel = f.str("hotel", False, 150)
    itin = f.text("itin", True)
    inc = f.text("inc")
    exc = f.text("exc")
    pol = f.text("policy", True, 1000)
    v = f.check()
    lines = lambda s: [x.strip() for x in s.split("\n") if x.strip()]
    t = Tour.objects.create(name=name, dest=dest, region=region, days=days, price=price, cost=cost, supplier=get(Supplier, v["sup"], "Supplier") if v["sup"] else None,
                            transport=tr, hotel=hotel, itinerary=lines(itin), inclusions=lines(inc), exclusions=lines(exc), policy=pol,
                            color=["#1F5F57", "#3A5674", "#2F6B3F", "#7A3B2E", "#8A6A2B", "#4B5D3A"][Tour.objects.count() % 6])
    audit(ctx.user, "Tour package created", "Tours", t.name, next=money(price))
    return {"id": str(t.pk), "message": "Tour package created."}


@action("tour.policy", "settings.edit")
def tour_policy(ctx, d):
    t = get(Tour, d.get("id"), "Tour")
    pol = (d.get("policy") or "").strip()
    if not pol:
        raise ActionError("Enter the policy.", {"policy": "Required."})
    prev = t.policy
    t.policy = pol[:1000]
    t.save(update_fields=["policy"])
    audit(ctx.user, "Cancellation policy changed", "Tours", t.name, prev, t.policy, severity="Medium")
    return {"message": "Policy updated."}


@action("tour.departure", "umrah.create")
def tour_departure(ctx, d):
    t = get(Tour, d.get("id"), "Tour")
    f = Form(d)
    date = f.date("date", True)
    cap = f.int("capacity", True, 1, 1000)
    if date and date < timezone.localdate():
        f.err("date", "Choose a future date.")
    if date and t.departures.filter(date=date).exists():
        f.err("date", "A departure already exists on this date.")
    f.check()
    Departure.objects.create(tour=t, date=date, capacity=cap)
    audit(ctx.user, "Departure scheduled", "Tours", t.name, next=f"{date} · {cap} seats")
    return {"message": "Departure scheduled."}


# =============== Hotels & transport ===============

def _link(v):
    if not v:
        return None, None
    t, _, i = v.partition(":")
    if t == "g":
        g = get(UmrahGroup, i, "Group")
        return g, g.bookings.first()
    if t == "b":
        return None, get(Booking, i, "Booking")
    raise ActionError("Invalid link.")


@action("hotel.create", "umrah.create")
def hotel_create(ctx, d):
    f = Form(d)
    for k, m in (("hotel", 150), ("city", 80), ("country", 80), ("room", 60)):
        f.str(k, True, m)
    f.str("supplierId", True)
    f.int("rooms", True, 1, 500)
    ci = f.date("checkIn", True)
    co = f.date("checkOut", True)
    if ci and co and co <= ci:
        f.err("checkOut", "Check-out must be after check-in.")
    f.str("conf", False, 40)
    f.choice("status", ["Pending confirmation", "Confirmed", "Cancelled"])
    v = f.check()
    g, b = _link(d.get("link"))
    h = HotelReservation.objects.create(hotel=v["hotel"], city=v["city"], country=v["country"], supplier=get(Supplier, v["supplierId"], "Supplier"), room=v["room"],
                                        rooms=v["rooms"], check_in=ci, check_out=co, conf=v["conf"], status=v["status"], group=g, booking=b)
    audit(ctx.user, "Hotel reservation added", "Hotels", h.hotel, next=h.status)
    return {"message": "Hotel reservation added."}


@action("hotel.confirm", "umrah.edit")
def hotel_confirm(ctx, d):
    h = get(HotelReservation, d.get("id"), "Hotel")
    conf = (d.get("conf") or "").strip()
    if not conf:
        raise ActionError("Enter the confirmation reference.", {"conf": "Required."})
    h.conf, h.status = conf[:40], "Confirmed"
    h.save()
    audit(ctx.user, "Hotel confirmed", "Hotels", h.hotel, "Pending confirmation", "Confirmed · " + conf)
    return {"message": "Hotel confirmed."}


@action("transport.create", "umrah.create")
def transport_create(ctx, d):
    f = Form(d)
    for k in ("type", "from", "to"):
        f.str(k, True, 150)
    f.str("supplierId", True)
    at = f.str("at", True, 20)
    try:
        when = timezone.make_aware(dt.datetime.fromisoformat(at)) if at else None
    except ValueError:
        f.err("at", "Enter a valid date and time.")
        when = None
    f.int("pax", True, 1, 1000)
    f.choice("status", ["Pending confirmation", "Confirmed"])
    v = f.check()
    g, b = _link(d.get("link"))
    TransportArrangement.objects.create(type=v["type"], supplier=get(Supplier, v["supplierId"], "Supplier"), origin=v["from"], destination=v["to"], at=when,
                                        pax=v["pax"], status=v["status"], group=g, booking=b)
    audit(ctx.user, "Transport added", "Hotels", v["type"], next=v["status"])
    return {"message": "Transport arrangement added."}


# =============== Suppliers ===============

@action("supplier.save", lambda d: "supplier.edit" if d.get("id") else "supplier.create")
def supplier_save(ctx, d):
    f = Form(d)
    name = f.str("name", True, 150)
    cat = f.choice("cat", Supplier.CATEGORIES)
    terms = f.int("terms", True, 0, 365)
    v = {k: f.str(k, False, 120) for k in ("contact", "phone", "email", "ntn")}
    f.check()
    s = get(Supplier, d["id"], "Supplier") if d.get("id") else None
    if s:
        prev = f"{s.name} · {s.terms_days} days"
        s.name, s.category, s.terms_days = name, cat, terms
        for k, val in v.items():
            setattr(s, k, val)
        s.save()
        audit(ctx.user, "Supplier updated", "Suppliers", s.code, prev, f"{name} · {terms} days")
        return {"id": str(s.pk), "message": "Supplier updated."}
    s = Supplier.objects.create(code=next_ref("supplier", "SP-SU-", 3), name=name, category=cat, terms_days=terms, **v)
    audit(ctx.user, "Supplier created", "Suppliers", s.code, next=name)
    return {"id": str(s.pk), "message": "Supplier created."}


@action("supplierPayment.create", "supplier.create")
def supplier_payment(ctx, d):
    f = Form(d)
    f.str("supplierId", True)
    amount = f.money("amount", True, Decimal("1"))
    date = f.date("date", True)
    f.str("account", True)
    method = f.choice("method", ["Bank Transfer", "Cash", "Cheque"])
    tx = f.str("txRef", False, 60)
    notes = f.str("notes", False, 300)
    v = f.check()
    s = get(Supplier, v["supplierId"], "Supplier")
    bal = ledger.supplier_ledger(s)["balance"]
    if amount > bal:
        raise ActionError("Amount too high.", {"amount": f"Exceeds the payable balance of {money(bal)}."})
    acct = Account.objects.filter(code=v["account"], group__in=["Cash", "Bank"]).first()
    if not acct:
        raise ActionError("Choose a cash or bank account.", {"account": "Choose a cash or bank account."})
    ledger.assert_open(date)
    if ledger.account_balance(acct.code) < amount:
        raise ActionError("Insufficient balance.", {"amount": f"{acct.name} only has {money(ledger.account_balance(acct.code))} on the books."})
    p = SupplierPayment.objects.create(ref=next_ref("supplierpay", "SP-PV-"), supplier=s, date=date, amount=amount, account=acct, method=method, tx_ref=tx, by=ctx.emp, notes=notes)
    post(date, p.ref, f"Supplier payment · {s.name}", "Supplier payment", [("2000", amount, 0), (acct.code, 0, amount)], ctx.user)
    audit(ctx.user, "Supplier payment created", "Suppliers", p.ref, next=f"{money(amount)} · {s.name}", severity="Medium")
    return {"message": f"Supplier payment {p.ref} recorded."}


# =============== Expenses ===============

@action("expense.create", "expense.create")
def expense_create(ctx, d):
    f = Form(d)
    date = f.date("date", True)
    cat = f.choice("cat", list(Expense.CATEGORIES))
    desc = f.str("desc", True, 250)
    amount = f.money("amount", True, Decimal("1"))
    method = f.choice("method", ["Cash", "Bank Transfer", "Card"])
    f.str("account", True)
    f.str("branch", True)
    f.str("supplierId")
    v = f.check()
    ledger.assert_open(date)
    acct = Account.objects.filter(code=v["account"], group__in=["Cash", "Bank"]).first()
    if not acct:
        raise ActionError("Choose a cash or bank account.", {"account": "Choose a cash or bank account."})
    o = org()
    att = None
    if ctx.files.get("file"):
        att = store_document(ctx, ctx.files["file"], "Invoice", None, None, None)
    auto = amount <= o.expense_approval_limit
    e = Expense.objects.create(ref=next_ref("expense", "SP-EX-"), date=date, category=cat, desc=desc, amount=amount, method=method, account=acct,
                               branch=get(Branch, v["branch"], "Branch"), status="Approved" if auto else "Pending", submitted_by=ctx.emp,
                               approved_by="Auto-approved (under limit)" if auto else "", supplier=get(Supplier, v["supplierId"], "Supplier") if v["supplierId"] else None, attachment=att)
    if auto:
        post(date, e.ref, f"Expense · {desc}", "Expense", [(Expense.CATEGORIES[cat], amount, 0), (acct.code, 0, amount)], ctx.user)
    audit(ctx.user, "Expense submitted", "Expenses", e.ref, next=f"{money(amount)} · {e.status}")
    return {"message": f"Expense {e.ref} recorded." if auto else f"Expense {e.ref} submitted for approval."}


@action("expense.decide", "expense.approve")
def expense_decide(ctx, d):
    e = get(Expense, d.get("id"), "Expense")
    if e.status != "Pending":
        raise ActionError("Only pending expenses can be approved or rejected.")
    if d.get("decision") == "approve":
        if e.submitted_by_id == ctx.emp.pk and ctx.emp.role not in ("Administrator", "Owner"):
            raise ActionError("You cannot approve an expense you submitted.")
        ledger.assert_open(e.date)
        post(e.date, e.ref, f"Expense · {e.desc}", "Expense", [(Expense.CATEGORIES[e.category], e.amount, 0), (e.account.code, 0, e.amount)], ctx.user)
        e.status, e.approved_by = "Approved", ctx.name
        e.save()
        audit(ctx.user, "Expense approved", "Expenses", e.ref, "Pending", "Approved", severity="Medium")
        return {"message": f"{e.ref} approved and posted."}
    reason = (d.get("reason") or "").strip()
    if not reason:
        raise ActionError("A reason is required.", {"reason": "Required."})
    e.status, e.reject_reason, e.approved_by = "Rejected", reason[:300], ctx.name
    e.save()
    audit(ctx.user, "Expense rejected", "Expenses", e.ref, "Pending", "Rejected", reason, "Medium")
    return {"message": f"{e.ref} rejected."}


# =============== Refunds ===============

def refundable(b, cancel_fee, fee):
    fig = figures(b)
    base = b.cancel_fee if b.cancelled_on else cancel_fee
    return fig["paid"] - fig["refunded"] - (base or ZERO) - fee


@action("refund.request", "refund.create")
def refund_request(ctx, d):
    f = Form(d)
    f.str("bookingId", True)
    cfee = f.money("cancelFee")
    fee = f.money("fee")
    req = f.money("requested", True, Decimal("1"))
    method = f.choice("method", ["Bank Transfer", "Cash", "Card"])
    reason = f.text("reason", True, 300)
    v = f.check()
    b = get(Booking, v["bookingId"], "Booking")
    if b.status == "Refunded":
        raise ActionError("This booking is already refunded.")
    if b.refunds.exclude(status__in=["Completed", "Rejected"]).exists():
        raise ActionError("This booking already has an open refund request.")
    if b.cancelled_on:
        cfee = b.cancel_fee or ZERO
    elif cfee > b.price:
        raise ActionError("Too high.", {"cancelFee": "Cannot exceed the booking price."})
    mx = refundable(b, cfee, fee)
    if req > mx:
        raise ActionError("Amount too high.", {"requested": f"Cannot exceed {money(max(ZERO, mx))} (paid minus charges)."})
    r = Refund.objects.create(ref=next_ref("refund", "SP-RF-"), booking=b, payment=b.payments.filter(status="Posted").order_by("id").first(), requested=req,
                              cancel_fee=cfee, fee=fee, method=method, reason=reason, requested_by=ctx.name,
                              history=[{"at": now_label(), "text": f"Refund requested · {money(req)}", "by": ctx.name}])
    tl(b, f"Refund {r.ref} requested · {money(req)}", ctx)
    b.save(update_fields=["timeline"])
    audit(ctx.user, "Refund requested", "Refunds", r.ref, next=money(req), reason=reason, severity="Medium")
    return {"message": f"Refund {r.ref} requested."}


@action("refund.step", "refund.create")
def refund_step(ctx, d):
    r = get(Refund, d.get("id"), "Refund")
    nxt = {"Requested": "Under Review", "Under Review": "Awaiting Approval", "Approved": "Processing"}.get(r.status)
    if not nxt:
        raise ActionError("This refund cannot move forward from its current stage.")
    if r.status == "Approved" and not has_perm(ctx.user, "refund.approve"):
        raise ActionError("Your role cannot process approved refunds.", status=403)
    prev = r.status
    r.status = nxt
    r.history.append({"at": now_label(), "text": f"{prev} → {nxt}", "by": ctx.name})
    r.save()
    audit(ctx.user, "Refund status changed", "Refunds", r.ref, prev, nxt)
    return {"message": f"{r.ref} moved to {nxt}."}


@action("refund.approve", "refund.approve")
def refund_approve(ctx, d):
    r = get(Refund, d.get("id"), "Refund")
    if r.status != "Awaiting Approval":
        raise ActionError("Only refunds awaiting approval can be approved.")
    b = r.booking
    f = Form(d)
    amt = f.money("approved", True, Decimal("1"))
    sc = f.money("supplierCredit", False, max_value=b.cost)
    note = f.str("note", False, 200)
    f.check()
    mx = refundable(b, r.cancel_fee, r.fee)
    if amt > mx:
        raise ActionError("Too high.", {"approved": f"Cannot exceed {money(max(ZERO, mx))}."})
    if amt > org().refund_approval_limit and ctx.emp.role not in ("Administrator", "Owner"):
        raise ActionError("Limit exceeded.", {"approved": f"Refunds above {money(org().refund_approval_limit)} need an Administrator."})
    if not b.cancelled_on:
        cancel_booking(b, r.cancel_fee, sc, "Refund " + r.ref, ctx.user)
        tl(b, f"Cancelled for refund {r.ref} · charges kept {money(r.cancel_fee)}", ctx)
        b.save()
        _reverse_open_commissions(b, "Booking cancelled for refund")
        r.supplier_credit = sc
    r.status, r.approved, r.approved_by = "Approved", amt, ctx.name
    r.history.append({"at": now_label(), "text": f"Approved · {money(amt)}" + (f" — {note}" if note else ""), "by": ctx.name})
    r.save()
    audit(ctx.user, "Refund approved", "Refunds", r.ref, "Awaiting Approval", f"Approved · {money(amt)}", severity="High")
    return {"message": f"{r.ref} approved for {money(amt)}."}


@action("refund.complete", "refund.approve")
def refund_complete(ctx, d):
    r = Refund.objects.select_for_update().get(pk=int(d.get("id")))
    if r.status == "Completed" or r.completed_on:
        raise ActionError("This refund is already completed. No second payout was created.")
    if r.status not in ("Approved", "Processing"):
        raise ActionError("Approve the refund before paying it.")
    b = r.booking
    fig = figures(b)
    if r.approved + r.fee > fig["paid"] - fig["refunded"] - (b.cancel_fee or ZERO):
        raise ActionError("The approved amount is higher than the customer's credit. Review the refund.")
    t = timezone.localdate()
    acct = ledger.account_for_method(r.method, b.branch)
    if ledger.account_balance(acct.code) < r.approved:
        raise ActionError(f"{acct.name} only has {money(ledger.account_balance(acct.code))} on the books — record the refund from another account.")
    if r.fee:
        post(t, r.ref + "-F", "Refund processing fee", "Refund", [("1100", r.fee, 0), ("4040", 0, r.fee)], ctx.user, b)
    post(t, r.ref, f"Refund paid · {ledger.party_name(b)}", "Refund", [("1100", r.approved, 0), (acct.code, 0, r.approved)], ctx.user, b)
    r.status, r.completed_on = "Completed", t
    r.history.append({"at": now_label(), "text": f"Paid · {money(r.approved)} by {r.method}", "by": ctx.name})
    r.save()
    b.status = "Refunded"
    tl(b, f"Refund {r.ref} paid · {money(r.approved)}", ctx)
    b.save()
    audit(ctx.user, "Refund completed", "Refunds", r.ref, "Processing", f"Completed · {money(r.approved)}", severity="High")
    return {"message": f"Refund {r.ref} completed. {money(r.approved)} paid out."}


@action("refund.reject", "refund.approve")
def refund_reject(ctx, d):
    r = get(Refund, d.get("id"), "Refund")
    reason = (d.get("reason") or "").strip()
    if not reason:
        raise ActionError("A reason is required.", {"reason": "Required."})
    if r.status in ("Completed", "Rejected", "Approved", "Processing"):
        raise ActionError(f"A {r.status.lower()} refund cannot be rejected.")
    prev = r.status
    r.status, r.reject_reason, r.approved_by = "Rejected", reason[:300], ctx.name
    r.history.append({"at": now_label(), "text": "Rejected — " + reason, "by": ctx.name})
    r.save()
    audit(ctx.user, "Refund rejected", "Refunds", r.ref, prev, "Rejected", reason, "Medium")
    return {"message": f"{r.ref} rejected."}


# =============== Commissions ===============

@action("commission.decide", "commission.approve")
def commission_decide(ctx, d):
    c = get(Commission, d.get("id"), "Commission")
    act = d.get("decision")
    if c.kind == "Supplier commission (earned)":
        raise ActionError("Earned supplier commission is netted in the ticket cost; nothing to pay.")
    if act == "approve" and c.status == "Pending":
        c.status = "Approved"
    elif act == "pay" and c.status == "Approved":
        t = timezone.localdate()
        post(t, c.ref, f"{c.kind} paid · {c.party}", "Commission", [("6060", c.amount, 0), ("1010", 0, c.amount)], ctx.user, c.booking)
        c.status, c.paid_on = "Paid", t
    elif act == "reverse" and c.status in ("Pending", "Approved"):
        if not has_perm(ctx.user, "commission.reverse"):
            raise ActionError("Your role cannot reverse commissions.", status=403)
        reason = (d.get("reason") or "").strip()
        if not reason:
            raise ActionError("A reason is required.", {"reason": "Required."})
        c.status, c.reverse_reason = "Reversed", reason[:300]
    else:
        raise ActionError(f"Cannot {act} a {c.status.lower()} commission.")
    prev = c.status
    c.save()
    audit(ctx.user, f"Commission {c.status.lower()}", "Commissions", c.ref, next=f"{c.status} · {money(c.amount)}", severity="Medium")
    return {"message": f"{c.ref} {c.status.lower()}."}


@action("commRule.update", "settings.edit")
def comm_rule(ctx, d):
    r = get(CommissionRule, d.get("id"), "Rule")
    f = Form(d)
    basis = f.choice("basis", CommissionRule.BASES)
    rate = f.number("rate", True, 0, 1000000)
    if basis and basis.startswith("%") and rate is not None and rate > 100:
        f.err("rate", "A percentage cannot exceed 100.")
    f.check()
    prev = f"{r.basis} {r.rate}"
    r.basis, r.rate = basis, rate
    r.save()
    audit(ctx.user, "Commission rule changed", "Commissions", f"{r.kind} · {r.service}", prev, f"{basis} {rate}", severity="High")
    return {"message": "Rule updated. It applies to bookings confirmed from now on."}


# =============== Accounting ===============

@action("journal.create", "journal.create")
def journal_create(ctx, d):
    f = Form(d)
    date = f.date("date", True)
    memo = f.str("memo", True, 200)
    f.check()
    lines = []
    for i, l in enumerate(d.get("lines") or []):
        code = str(l.get("acct") or "")
        dr, cr = D(l.get("dr") or 0), D(l.get("cr") or 0)
        if not code and not dr and not cr:
            continue
        if code in ledger.CONTROL_ACCOUNTS:
            raise ActionError("Receivable and payable control accounts are updated only through bookings, receipts and supplier payments.")
        if not code:
            raise ActionError(f"Choose an account on line {i + 1}.")
        lines.append((code, dr, cr))
    if len(lines) < 2:
        raise ActionError("A journal needs at least two lines.")
    ref = next_ref("journal", "JV-")
    post(date, ref, memo, "Manual journal", lines, ctx.user)
    audit(ctx.user, "Journal posted", "Accounting", ref, next=memo, severity="High")
    return {"message": f"Journal {ref} posted."}


@action("transfer.create", "journal.create")
def transfer_create(ctx, d):
    f = Form(d)
    fr = f.str("from", True)
    to = f.str("to", True)
    amount = f.money("amount", True, Decimal("1"))
    date = f.date("date", True)
    memo = f.str("memo", False, 200) or "Internal transfer"
    if fr == to:
        f.err("to", "Choose a different account.")
    f.check()
    for c in (fr, to):
        if not Account.objects.filter(code=c, group__in=["Cash", "Bank"]).exists():
            raise ActionError("Transfers are between cash and bank accounts only.")
    if ledger.account_balance(fr, upto=date) < amount:
        raise ActionError("Insufficient balance.", {"amount": f"Exceeds the book balance of {money(ledger.account_balance(fr, upto=date))}."})
    ref = next_ref("transfer", "TR-")
    post(date, ref, memo, "Transfer", [(to, amount, 0), (fr, 0, amount)], ctx.user)
    audit(ctx.user, "Internal transfer", "Cash & Bank", ref, next=f"{money(amount)} {fr} → {to}", severity="Medium")
    return {"message": "Transfer recorded."}


@action("period.close", "journal.approve")
def period_close(ctx, d):
    p = get(Period, d.get("id"), "Period")
    if p.status == "Closed":
        raise ActionError("Already closed.")
    if p.end >= timezone.localdate():
        raise ActionError("A period can only be closed after its last day.")
    reason = (d.get("reason") or "").strip()
    p.status, p.closed_by, p.closed_on = "Closed", ctx.name, timezone.localdate()
    p.save()
    audit(ctx.user, "Financial period closed", "Accounting", p.name, "Open", "Closed", reason, "Critical")
    return {"message": f"{p.name} closed."}


@action("period.create", "journal.approve")
def period_create(ctx, d):
    f = Form(d)
    name = f.str("name", True, 80)
    s = f.date("start", True)
    e = f.date("end", True)
    if s and e and e < s:
        f.err("end", "End must be after start.")
    if s and e and Period.objects.filter(start__lte=e, end__gte=s).exists():
        f.err("start", "Overlaps an existing period.")
    f.check()
    Period.objects.create(name=name, start=s, end=e)
    audit(ctx.user, "Financial period created", "Accounting", name, severity="Medium")
    return {"message": "Period created."}


# =============== Cash & bank ===============

def closing_figures(acct_code, day):
    from finance.models import JournalLine
    opening = ledger.account_balance(acct_code, upto=day - dt.timedelta(days=1))
    lines = JournalLine.objects.filter(account__code=acct_code, entry__date=day).select_related("entry")
    rec = sum((l.debit for l in lines), ZERO)
    refunds = sum((l.credit for l in lines if l.entry.source == "Refund"), ZERO)
    pay = sum((l.credit for l in lines), ZERO) - refunds
    return {"open": opening, "rec": rec, "pay": pay, "refunds": refunds, "exp": opening + rec - pay - refunds}


@action("closing.create", "cash.create")
def closing_create(ctx, d):
    f = Form(d)
    code = f.str("account", True)
    counted = f.money("counted", True)
    note = f.text("note", False, 300)
    f.check()
    acct = Account.objects.filter(code=code, group="Cash").first()
    if not acct:
        raise ActionError("Choose a cash account.", {"account": "Choose a cash account."})
    t = timezone.localdate()
    c = closing_figures(code, t)
    diff = counted - c["exp"]
    if diff and not note:
        raise ActionError("Explain the difference.", {"note": "Explain the difference before saving."})
    br = acct.branches.first()
    cl = CashClosing.objects.create(ref=f"CL-{br.code if br else code}-{t:%m%d}-{Sequence.next('closing')}", date=t, account=acct, opening=c["open"], receipts=c["rec"],
                                    payments=c["pay"] + c["refunds"], expected=c["exp"], counted=counted, diff=diff,
                                    status="Discrepancy — pending review" if diff else "Balanced", note=note, by=ctx.name)
    audit(ctx.user, "Cash closing recorded", "Cash & Bank", cl.ref, next=f"Difference {money(diff)}" if diff else "Balanced", severity="High" if diff else "Info")
    return {"message": f"Closing saved with a difference of {money(diff)}. It needs review." if diff else "Cash balanced. Closing saved."}


@action("closing.approve", "cash.approve")
def closing_approve(ctx, d):
    c = get(CashClosing, d.get("id"), "Closing")
    reason = (d.get("reason") or "").strip()
    if not reason:
        raise ActionError("A reason is required.", {"reason": "Required."})
    if c.adj_posted or not c.diff:
        raise ActionError("Nothing to adjust.")
    t = timezone.localdate()
    lines = [("6095", -c.diff, 0), (c.account.code, 0, -c.diff)] if c.diff < 0 else [(c.account.code, c.diff, 0), ("6095", 0, c.diff)]
    post(t, c.ref, f"Cash over/short · {c.account.name}", "Cash closing", lines, ctx.user)
    c.adj_posted, c.status, c.adj_reason = True, "Adjusted — approved", reason[:300]
    c.save()
    audit(ctx.user, "Cash adjustment approved", "Cash & Bank", c.ref, "Discrepancy", f"Adjusted {money(c.diff)}", reason, "High")
    return {"message": "Adjustment posted."}


@action("bank.match", "cash.edit")
def bank_match(ctx, d):
    e = get(JournalEntry, d.get("entryId"), "Entry")
    if d.get("matched"):
        BankMatch.objects.get_or_create(entry=e, defaults={"matched_by": ctx.user})
    else:
        BankMatch.objects.filter(entry=e).delete()
    return {}


@action("bank.statement", "cash.edit")
def bank_statement(ctx, d):
    o = org()
    v = d.get("value")
    o.bank_statement_balance = None if v in (None, "") else D(v)
    o.save(update_fields=["bank_statement_balance"])
    return {}


# =============== Employees ===============

@action("employee.save", "settings.create")
def employee_save(ctx, d):
    f = Form(d)
    name = f.str("name", True, 120)
    role = f.choice("role", ROLES)
    f.str("branch", True)
    email = f.str("email", False, 120)
    phone = f.str("phone", False, 40)
    username = f.str("username", False, 40)
    pw = d.get("password") or ""
    User = get_user_model()
    if role == "Owner" and ctx.emp.role != "Owner" and ctx.emp.role != "Administrator":
        f.err("role", "Only an Administrator can create owners.")
    if username and User.objects.filter(username__iexact=username).exists():
        f.err("username", "This username is taken.")
    if username:
        try:
            validate_password(pw, User(username=username, first_name=name))
        except ValidationError as e:
            f.err("password", " ".join(e.messages))
    v = f.check()
    n = Sequence.next("employee", Employee.objects.count())
    e = Employee.objects.create(code=f"EMP-{n:03d}", name=name, role=role, branch=get(Branch, v["branch"], "Branch"), email=email, phone=phone)
    if username:
        e.user = User.objects.create_user(username=username, password=pw, email=email, first_name=name)
        e.save()
    audit(ctx.user, "Employee added", "Employees", e.code, next=f"{name} · {role}" + (f" · login {username}" if username else ""), severity="High")
    return {"message": f"{name} added." + (" They can now sign in." if username else "")}


@action("employee.role", "settings.edit")
def employee_role(ctx, d):
    e = get(Employee, d.get("id"), "Employee")
    f = Form(d)
    role = f.choice("role", ROLES)
    f.str("branch", True)
    reason = f.str("reason", True, 300)
    v = f.check()
    if e.pk == ctx.emp.pk and role not in ("Administrator", "Owner"):
        raise ActionError("You cannot remove your own administrator rights.")
    prev = f"{e.role} · {e.branch.code}"
    e.role, e.branch = role, get(Branch, v["branch"], "Branch")
    e.save()
    audit(ctx.user, "Employee permissions modified", "Employees", e.code, prev, f"{role} · {e.branch.code}", reason, "High")
    return {"message": "Role updated. It takes effect on the employee's next request."}


@action("employee.status", "settings.edit")
def employee_status(ctx, d):
    e = get(Employee, d.get("id"), "Employee")
    if e.pk == ctx.emp.pk:
        raise ActionError("You cannot suspend your own account.")
    reason = (d.get("reason") or "").strip()
    if not reason:
        raise ActionError("A reason is required.", {"reason": "Required."})
    prev = e.status
    e.status = "Suspended" if e.status == "Active" else "Active"
    e.save()
    if e.status == "Suspended" and e.user_id:
        from django.contrib.sessions.models import Session
        for s in Session.objects.all():
            if s.get_decoded().get("_auth_user_id") == str(e.user_id):
                s.delete()
    audit(ctx.user, "Employee status changed", "Employees", e.code, prev, e.status, reason, "High")
    return {"message": f"{e.name} is now {e.status.lower()}."}


@action("employee.login", "settings.edit")
def employee_login(ctx, d):
    e = get(Employee, d.get("id"), "Employee")
    User = get_user_model()
    f = Form(d)
    username = f.str("username", not e.user_id, 40)
    pw = d.get("password") or ""
    if username and User.objects.filter(username__iexact=username).exclude(pk=e.user_id).exists():
        f.err("username", "This username is taken.")
    try:
        validate_password(pw, User(username=username or (e.user.username if e.user_id else ""), first_name=e.name))
    except ValidationError as ex:
        f.err("password", " ".join(ex.messages))
    f.check()
    if e.user_id:
        e.user.set_password(pw)
        if username:
            e.user.username = username
        e.user.save()
        audit(ctx.user, "Password reset", "Employees", e.code, severity="High")
        return {"message": f"Password reset for {e.name}."}
    e.user = User.objects.create_user(username=username, password=pw, email=e.email, first_name=e.name)
    e.save()
    audit(ctx.user, "Login created", "Employees", e.code, next=username, severity="High")
    return {"message": f"Login created for {e.name}."}


@action("me.password", None)
def my_password(ctx, d):
    if not ctx.user.check_password(d.get("current") or ""):
        raise ActionError("Current password is incorrect.", {"current": "Incorrect password."})
    pw = d.get("new") or ""
    if pw != (d.get("confirm") or ""):
        raise ActionError("Passwords do not match.", {"confirm": "Passwords do not match."})
    try:
        validate_password(pw, ctx.user)
    except ValidationError as e:
        raise ActionError("Choose a stronger password.", {"new": " ".join(e.messages)})
    ctx.user.set_password(pw)
    ctx.user.save()
    audit(ctx.user, "Password changed", "Employees", ctx.user.username, severity="Medium")
    return {"message": "Password changed. Sign in again with your new password.", "relogin": True}


# =============== Branches ===============

@action("branch.create", "settings.create")
def branch_create(ctx, d):
    f = Form(d)
    code = f.str("code", True, 6, pattern=r"[A-Za-z0-9]{2,6}", pattern_msg="Use 2–6 letters or digits.").upper()
    name = f.str("name", True, 120)
    city = f.str("city", True, 80)
    addr = f.str("address", False, 250)
    phone = f.str("phone", False, 40)
    if code and Branch.objects.filter(code=code).exists():
        f.err("code", "This branch code is already used.")
    f.check()
    b = Branch.objects.create(code=code, name=name, city=city, address=addr, phone=phone, cash_account=ledger.new_cash_account(city))
    audit(ctx.user, "Branch created", "Branches", code, next=name, severity="Medium")
    return {"message": f"{name} created with its own cash account ({b.cash_account.code})."}


# =============== Sub-agents ===============

@action("agent.save", "agent.create")
def agent_save(ctx, d):
    f = Form(d)
    name = f.str("name", True, 150)
    city = f.str("city", True, 80)
    contact = f.str("contact", True, 40)
    limit = f.money("limit", True)
    rate = f.number("rate", True, 0, 100)
    opening = f.money("opening")
    f.check()
    a = Agent.objects.create(code=next_ref("agent", "SP-AG-", 3, 100), name=name, city=city, contact=contact, credit_limit=limit, commission_rate=rate,
                             opening_balance=opening, branch=ctx.emp.branch)
    if opening > 0:
        post(timezone.localdate(), a.code + "-OB", f"Opening balance owed by {name}", "Opening", [("1100", opening, 0), ("3000", 0, opening)], ctx.user)
    audit(ctx.user, "Sub-agent registered", "Sub-Agents", a.code, next=name)
    return {"message": f"{name} registered and waiting for approval."}


@action("agent.approve", "agent.approve")
def agent_approve(ctx, d):
    a = get(Agent, d.get("id"), "Agent")
    prev = a.status
    a.status = "Active" if a.status != "Active" else "Suspended"
    a.save(update_fields=["status"])
    audit(ctx.user, "Sub-agent status changed", "Sub-Agents", a.code, prev, a.status, severity="Medium")
    return {"message": f"{a.name} is now {a.status.lower()}."}


@action("agent.limit", "agent.approve")
def agent_limit(ctx, d):
    a = get(Agent, d.get("id"), "Agent")
    f = Form(d)
    limit = f.money("limit", True)
    reason = f.str("reason", True, 300)
    f.check()
    prev = money(a.credit_limit)
    a.credit_limit = limit
    a.save(update_fields=["credit_limit"])
    audit(ctx.user, "Credit limit changed", "Sub-Agents", a.code, prev, money(limit), reason, "High")
    return {"message": "Credit limit updated."}


def agent_balance(a):
    from finance.ledger import paid_map, refund_map
    bks = list(a.bookings.all())
    pm, rm = paid_map([b.id for b in bks]), refund_map([b.id for b in bks])
    return a.opening_balance + sum((ledger.charged(b) - pm.get(b.id, ZERO) + rm.get(b.id, ZERO) for b in bks), ZERO)


@action("agentReq.create", "agent.create")
def agent_req_create(ctx, d):
    f = Form(d)
    f.str("agentId", True)
    service = f.choice("service", SERVICES)
    desc = f.str("desc", True, 250)
    pax = f.int("pax", True, 1, 500)
    td = f.date("travelDate", True)
    amount = f.money("amount", True, Decimal("1"))
    cost = f.money("cost", True)
    f.str("supplierId")
    v = f.check()
    if cost > 0 and not v["supplierId"]:
        raise ActionError("Choose a supplier.", {"supplierId": "Choose the supplier for this cost."})
    AgentRequest.objects.create(agent=get(Agent, v["agentId"], "Agent"), service=service, desc=desc, pax=pax, travel_date=td, amount=amount, cost=cost,
                                supplier=get(Supplier, v["supplierId"], "Supplier") if v["supplierId"] else None)
    audit(ctx.user, "Agent request logged", "Sub-Agents", desc[:60], next=money(amount))
    return {"message": "Request logged. Approve it to create the booking."}


@action("agentReq.decide", "agent.approve")
def agent_req_decide(ctx, d):
    q = get(AgentRequest, d.get("id"), "Request")
    if q.status != "Pending":
        raise ActionError("This request has already been decided.")
    a = q.agent
    if d.get("decision") == "reject":
        reason = (d.get("reason") or "").strip()
        if not reason:
            raise ActionError("A reason is required.", {"reason": "Required."})
        q.status, q.reason = "Rejected", reason[:250]
        q.save()
        audit(ctx.user, "Agent request rejected", "Sub-Agents", a.code, reason=reason)
        return {"message": "Request rejected."}
    if a.status != "Active":
        raise ActionError(f"{a.name} is {a.status.lower()} and cannot book.")
    bal = agent_balance(a)
    if bal + q.amount > a.credit_limit:
        audit(ctx.user, "Credit check blocked booking", "Sub-Agents", a.code, next=f"Needed {money(bal + q.amount)} of {money(a.credit_limit)}", severity="Medium")
        raise ActionError(f"Credit limit exceeded: {a.name} owes {money(bal)}; this request would take them to {money(bal + q.amount)}, above the {money(a.credit_limit)} limit.")
    b = new_booking(ctx, status="Confirmed", agent=a, service=q.service, destination=q.desc[:200], travel_date=q.travel_date, pax=q.pax,
                    passengers=[f"Agent client group ({q.pax})"], price=q.amount, cost=q.cost, supplier=q.supplier, employee=ctx.emp, branch=a.branch,
                    notes="Agent request: " + q.desc)
    q.status, q.booking = "Approved", b
    q.save()
    audit(ctx.user, "Agent booking approved", "Sub-Agents", b.ref, next=f"{a.name} · {money(q.amount)}")
    return {"message": f"Approved. Booking {b.ref} created on {a.name}'s account ({money(bal + q.amount)} of {money(a.credit_limit)} used)."}


# =============== Documents ===============

def store_document(ctx, upload, doc_type, customer, booking, expiry):
    import os
    name = os.path.basename(upload.name or "file")[:200]
    ext = os.path.splitext(name)[1].lower()
    if ext not in settings.ALLOWED_DOCUMENT_EXTENSIONS:
        raise ActionError("File type not allowed.", {"file": "Allowed: " + ", ".join(sorted(settings.ALLOWED_DOCUMENT_EXTENSIONS))})
    if upload.size > settings.MAX_DOCUMENT_BYTES:
        raise ActionError("File too large.", {"file": f"Maximum size is {settings.MAX_DOCUMENT_BYTES // (1024 * 1024)} MB."})
    head = upload.read(8)
    upload.seek(0)
    sig_ok = {".pdf": head.startswith(b"%PDF"), ".png": head.startswith(b"\x89PNG"), ".jpg": head.startswith(b"\xff\xd8"), ".jpeg": head.startswith(b"\xff\xd8"),
              ".webp": head[:4] == b"RIFF", ".docx": head.startswith(b"PK"), ".xlsx": head.startswith(b"PK")}[ext]
    if not sig_ok:
        raise ActionError("File content does not match its extension.", {"file": "The file appears damaged or is not really a " + ext + " file."})
    stored = uuid.uuid4().hex + ext
    sub = settings.DOCUMENTS_ROOT / timezone.localdate().strftime("%Y-%m")
    sub.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    tmp = sub / (stored + ".part")
    with open(tmp, "wb") as out:
        for chunk in upload.chunks():
            h.update(chunk)
            out.write(chunk)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, sub / stored)
    ctype = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
             ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[ext]
    return Document.objects.create(type=doc_type, original_name=name, stored_name=f"{sub.name}/{stored}", size=upload.size, content_type=ctype, sha256=h.hexdigest(),
                                   customer=customer, booking=booking, uploaded_by=ctx.name, expiry=expiry)


@action("document.upload", "customer.edit")
def document_upload(ctx, d):
    f = Form(d)
    t = f.choice("type", Document.TYPES)
    f.str("customerId", True)
    f.str("bookingId")
    exp = f.date("expiry")
    if not ctx.files.get("file"):
        f.err("file", "Choose a file.")
    v = f.check()
    doc = store_document(ctx, ctx.files["file"], t, get(Customer, v["customerId"], "Customer"), get(Booking, v["bookingId"], "Booking") if v["bookingId"] else None, exp)
    audit(ctx.user, "Document uploaded", "Documents", doc.original_name, next=t)
    return {"id": str(doc.pk), "message": "Document uploaded and waiting for verification."}


@action("document.verify", "customer.edit")
def document_verify(ctx, d):
    doc = get(Document, d.get("id"), "Document")
    doc.status = "Verified"
    doc.save(update_fields=["status"])
    audit(ctx.user, "Document verified", "Documents", doc.original_name, "Pending verification", "Verified", severity="Low")
    return {"message": "Document verified."}


# =============== Settings, notifications, backups ===============

@action("settings.save", "settings.edit")
def settings_save(ctx, d):
    o = org()
    f = Form(d)
    changes = []
    text_fields = {"org.name": ("name", 120), "org.city": ("city", 80), "org.address": ("address", 250), "org.phone": ("phone", 40), "org.email": ("email", 120),
                   "org.ntn": ("ntn", 40), "settings.receiptPrefix": ("receipt_prefix", 12), "settings.bookingPrefix": ("booking_prefix", 12)}
    for k, (attr, m) in text_fields.items():
        if k in d:
            val = f.str(k, attr == "name", m)
            if getattr(o, attr) != val:
                changes.append((attr, getattr(o, attr), val))
    num_fields = {"settings.creditDays": "credit_days", "settings.discountLimit": "discount_limit"}
    for k, attr in num_fields.items():
        if k in d:
            val = f.int(k, True, 0, 365)
            if val is not None and getattr(o, attr) != val:
                changes.append((attr, getattr(o, attr), val))
    for k, attr in {"settings.expenseLimit": "expense_approval_limit", "settings.refundApprovalLimit": "refund_approval_limit"}.items():
        if k in d:
            val = f.money(k, True)
            if getattr(o, attr) != val:
                changes.append((attr, getattr(o, attr), val))
    for k, attr in {"settings.allowOverpayment": "allow_overpayment", "settings.docsRequired": "visa_docs_required"}.items():
        if k in d:
            val = f.bool(k)
            if getattr(o, attr) != val:
                changes.append((attr, getattr(o, attr), val))
    if "settings.methods" in d:
        ms = [m.strip()[:30] for m in str(d["settings.methods"]).split(",") if m.strip()]
        if "Cash" not in ms:
            f.err("settings.methods", "Keep “Cash” in the list.")
        if ms != o.payment_methods:
            changes.append(("payment_methods", ", ".join(o.payment_methods), ms))
    if "settings.visaDocs" in d:
        docs = [x.strip()[:150] for x in str(d["settings.visaDocs"]).split("\n") if x.strip()]
        if docs != o.visa_docs:
            changes.append(("visa_docs", len(o.visa_docs), docs))
    f.check()
    if not changes:
        return {"message": "No changes to save."}
    for attr, _, val in changes:
        setattr(o, attr, val)
    o.save()
    audit(ctx.user, "Settings changed", "Settings", d.get("_section", "settings"), "; ".join(f"{a}: {p}" for a, p, _ in changes)[:500],
          "; ".join(f"{a}: {v}" for a, _, v in changes)[:500], severity="Medium")
    return {"message": "Settings saved."}


@action("notif.prefs", "settings.edit")
def notif_prefs(ctx, d):
    o = org()
    prefs = o.notification_prefs
    cat, ch = d.get("cat"), d.get("channel")
    if cat not in prefs or ch not in ("app", "email", "wa"):
        raise ActionError("Unknown preference.")
    prefs[cat][ch] = 1 if d.get("value") else 0
    o.notification_prefs = prefs
    o.save(update_fields=["notification_prefs"])
    return {}


@action("notif.read", None)
def notif_read(ctx, d):
    keys = d.get("keys") or ([d["key"]] if d.get("key") else [])
    for k in keys[:500]:
        NotificationState.objects.update_or_create(user=ctx.user, key=str(k)[:120], defaults={"read": bool(d.get("read", True))})
    return {}


@action("backup.create", "settings.edit")
def backup_create(ctx, d):
    from core.backup import create_backup
    path, manifest = create_backup(label="manual")
    audit(ctx.user, "Backup created", "Settings", path.name, next=f"{manifest['counts'].get('bookings', 0)} bookings, {manifest['documents']} documents", severity="Medium")
    return {"message": f"Backup saved: {path.name}", "file": path.name}
