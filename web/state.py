"""
Builds the data snapshot the interface renders from. Every collection is included only
if the signed-in user's role is allowed to view it (server-side enforcement).
Derived figures (balances, payment status, seats) are computed here, once, from the database.
"""
from pathlib import Path
import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from accounts.models import Employee
from accounts.permissions import PERM_ACTS, PERM_AREAS, ROLE_PERMS, perms_for, role_of
from core.backup import list_backups
from core.models import AuditLog, Branch, NotificationState, Organization
from crm.models import Communication, Customer, Document, Enquiry, Quote
from finance import ledger
from finance.models import (Account, BankMatch, CashClosing, Commission, CommissionRule, Expense, JournalEntry, JournalLine, Payment, Period,
                            Refund, SupplierPayment)
from operations.models import (Agent, AgentRequest, Booking, Departure, HotelReservation, Pilgrim, Supplier, Ticket, Tour, TransportArrangement,
                               UmrahGroup, UmrahPackage, VisaApplication)

ZERO = Decimal("0")


def m(x):
    if x is None:
        return None
    x = Decimal(x)
    return int(x) if x == x.to_integral_value() else float(x)


def d(x):
    return x.isoformat() if x else None


def dtl(x):
    return timezone.localtime(x).strftime("%Y-%m-%dT%H:%M") if x else None


def sid(x):
    return str(x) if x is not None else None


def build_state(user):
    P = perms_for(user)
    can = lambda p: p in P
    o = Organization.get()
    today = timezone.localdate()
    emp = getattr(user, "employee", None)
    S = {
        "today": today.isoformat(),
        "me": {"id": sid(emp.pk) if emp else None, "name": emp.name if emp else user.username, "role": role_of(user), "username": user.username,
               "branch": sid(emp.branch_id) if emp else None, "email": emp.email if emp else user.email},
        "perms": sorted(P),
        "roles": {r: sorted(v) for r, v in ROLE_PERMS.items()},
        "permAreas": PERM_AREAS, "permActs": PERM_ACTS,
        "app": {"name": settings.APP_NAME, "version": settings.APP_VERSION, "company": "Nexora", "demo": _demo_info()},
        "org": {"name": o.name, "city": o.city, "address": o.address, "phone": o.phone, "email": o.email, "ntn": o.ntn, "currency": o.currency,
                "tz": "Asia/Karachi (PKT, UTC+05:00)", "lang": "English", "sampleData": o.sample_data},
        "settings": {"creditDays": o.credit_days, "expenseLimit": m(o.expense_approval_limit), "refundApprovalLimit": m(o.refund_approval_limit),
                     "discountLimit": o.discount_limit, "allowOverpayment": o.allow_overpayment, "receiptPrefix": o.receipt_prefix,
                     "bookingPrefix": o.booking_prefix, "methods": o.payment_methods, "docsRequired": o.visa_docs_required, "visaDocs": o.visa_docs,
                     "notif": o.notification_prefs},
        "accounts": [{"code": a.code, "name": a.name, "type": a.type, "group": a.group} for a in Account.objects.all()],
        "branches": [{"id": sid(b.pk), "code": b.code, "name": b.name, "city": b.city, "address": b.address, "phone": b.phone, "status": b.status,
                      "manager": sid(b.manager_id), "cashAccount": b.cash_account.code} for b in Branch.objects.select_related("cash_account")],
    }
    full_emp = can("settings.view")
    S["employees"] = [dict({"id": sid(e.pk), "code": e.code, "name": e.name, "role": e.role, "branch": sid(e.branch_id), "status": e.status},
                           **({"email": e.email, "phone": e.phone, "joined": d(e.joined), "hasLogin": bool(e.user_id),
                               "username": e.user.username if e.user_id else "", "lastLogin": dtl(e.user.last_login) if e.user_id else None} if full_emp else {}))
                      for e in Employee.objects.select_related("user")]
    S["suppliers"] = [{"id": sid(s.pk), "code": s.code, "name": s.name, "cat": s.category, "terms": s.terms_days, "contact": s.contact, "phone": s.phone,
                       "email": s.email, "ntn": s.ntn, "status": s.status} for s in Supplier.objects.all()]

    view_cust = can("customer.view")
    S["customers"] = [{"id": sid(c.pk), "code": c.code, "name": c.name, "type": c.type, "city": c.city, "country": c.country, "phone": c.phone, "email": c.email,
                       "address": c.address, "cnic": c.cnic_masked, "passport": {"no": c.passport_masked, "expiry": d(c.passport_expiry)} if c.passport_masked else None,
                       "status": c.status, "branch": sid(c.branch_id), "created": d(c.created), "notes": c.notes}
                      for c in Customer.objects.all()] if view_cust else []

    view_bk = can("booking.view")
    bookings = list(Booking.objects.all()) if view_bk else []
    pm, rm = ledger.paid_map(), ledger.refund_map()
    S["bookings"] = []
    for b in bookings:
        f = ledger.figures(b, pm.get(b.id, ZERO), rm.get(b.id, ZERO), o.credit_days)
        S["bookings"].append({
            "id": sid(b.pk), "ref": b.ref, "customerId": sid(b.customer_id), "agentId": sid(b.agent_id), "service": b.service, "destination": b.destination,
            "travelDate": d(b.travel_date), "returnDate": d(b.return_date), "pax": b.pax, "passengers": b.passengers, "price": m(b.price), "cost": m(b.cost),
            "supplierId": sid(b.supplier_id), "status": b.status, "emp": sid(b.employee_id), "branch": sid(b.branch_id), "created": d(b.created),
            "postedOn": d(b.posted_on), "notes": b.notes, "depId": sid(b.departure_id), "groupId": sid(b.group_id), "airline": b.airline,
            "enquiryId": sid(b.enquiry_id),
            "cancel": {"date": d(b.cancelled_on), "fee": m(b.cancel_fee or 0), "reason": b.cancel_reason, "supplierCredit": m(b.supplier_credit)} if b.cancelled_on else None,
            "timeline": b.timeline, "paid": m(f["paid"]), "refunded": m(f["refunded"]), "charged": m(f["charged"]), "balance": m(f["balance"]),
            "outstanding": m(f["outstanding"]), "payStatus": f["pay_status"], "due": d(f["due"]),
        })
    agent_bal = {}
    for b in S["bookings"]:
        if b["agentId"]:
            agent_bal[b["agentId"]] = agent_bal.get(b["agentId"], 0) + b["balance"]

    S["payments"] = [{"id": sid(p.pk), "ref": p.ref, "bookingId": sid(p.booking_id), "customerId": sid(p.booking.customer_id), "agentId": sid(p.booking.agent_id),
                      "date": d(p.date), "method": p.method, "account": p.account.code, "amount": m(p.amount), "txRef": p.tx_ref, "by": sid(p.received_by_id),
                      "status": p.status, "branch": sid(p.branch_id), "notes": p.notes, "prevBal": m(p.prev_balance), "newBal": m(p.new_balance),
                      "reversedOn": d(p.reversed_on), "reverseReason": p.reverse_reason}
                     for p in Payment.objects.select_related("booking", "account")] if can("payment.view") else []
    S["tickets"] = [{"id": sid(t.pk), "bookingId": sid(t.booking_id), "customerId": sid(t.booking.customer_id), "passenger": t.passenger, "airline": t.airline,
                     "no": t.number, "pnr": t.pnr, "from": t.origin, "to": t.dest, "dep": d(t.dep), "ret": d(t.ret), "supplierId": sid(t.supplier_id),
                     "cost": m(t.cost), "sell": m(t.sell), "fee": m(t.fee), "comm": m(t.commission), "status": t.status, "emp": sid(t.employee_id),
                     "created": d(t.created), "branch": sid(t.booking.branch_id)} for t in Ticket.objects.select_related("booking")] if can("ticket.view") else []
    S["visas"] = [{"id": sid(v.pk), "ref": v.ref, "bookingId": sid(v.booking_id), "customerId": sid(v.booking.customer_id), "country": v.country, "type": v.type,
                   "status": v.status, "submitted": d(v.submitted), "expected": d(v.expected), "embassyFee": m(v.embassy_fee), "serviceFee": m(v.service_fee),
                   "officer": sid(v.officer_id), "created": d(v.created), "docs": v.docs, "timeline": v.timeline, "reminders": v.reminders, "notes": v.notes,
                   "branch": sid(v.booking.branch_id)} for v in VisaApplication.objects.select_related("booking")] if can("visa.view") else []

    view_um = can("umrah.view")
    S["umrahPkgs"] = [{"id": sid(p.pk), "name": p.name, "days": p.days, "makkah": p.makkah, "madinah": p.madinah, "transport": p.transport, "room": p.room,
                       "flight": p.flight, "cost": m(p.cost), "sell": m(p.sell), "capacity": p.capacity, "status": p.status, "inc": p.inclusions, "exc": p.exclusions}
                      for p in UmrahPackage.objects.all()] if view_um else []
    S["groups"] = [{"id": sid(g.pk), "ref": g.ref, "name": g.name, "pkgId": sid(g.package_id), "dep": d(g.departure), "ret": d(g.return_date), "flight": g.flight,
                    "retFlight": g.return_flight, "leader": g.leader, "status": g.status} for g in UmrahGroup.objects.all()] if view_um else []
    S["pilgrims"] = [{"id": sid(p.pk), "groupId": sid(p.group_id), "bookingId": sid(p.booking_id), "name": p.name, "gender": p.gender, "passport": p.passport_status,
                      "passportNo": p.passport_masked, "visa": p.visa_status, "room": p.room, "payment": p.payment_status, "emergency": p.emergency, "special": p.special}
                     for p in Pilgrim.objects.all()] if view_um else []
    S["tours"] = [{"id": sid(t.pk), "name": t.name, "dest": t.dest, "region": t.region, "days": t.days, "price": m(t.price), "cost": m(t.cost), "sup": sid(t.supplier_id),
                   "color": t.color, "transport": t.transport, "hotel": t.hotel, "itin": t.itinerary, "inc": t.inclusions, "exc": t.exclusions, "policy": t.policy,
                   "status": t.status} for t in Tour.objects.all()] if (view_um or view_bk) else []
    booked = {}
    for b in bookings:
        if b.departure_id and b.status not in ("Cancelled", "Refunded", "Draft"):
            booked[b.departure_id] = booked.get(b.departure_id, 0) + b.pax
    S["deps"] = [{"id": sid(x.pk), "tourId": sid(x.tour_id), "date": d(x.date), "capacity": x.capacity, "status": x.status, "booked": booked.get(x.pk, 0)}
                 for x in Departure.objects.all()] if (view_um or view_bk) else []
    S["hotels"] = [{"id": sid(h.pk), "hotel": h.hotel, "city": h.city, "country": h.country, "supplierId": sid(h.supplier_id), "room": h.room, "checkIn": d(h.check_in),
                    "checkOut": d(h.check_out), "rooms": h.rooms, "conf": h.conf, "status": h.status, "groupId": sid(h.group_id), "bookingId": sid(h.booking_id),
                    "contact": h.contact} for h in HotelReservation.objects.all()] if view_um else []
    S["transport"] = [{"id": sid(t.pk), "type": t.type, "supplierId": sid(t.supplier_id), "from": t.origin, "to": t.destination, "at": dtl(t.at), "pax": t.pax,
                       "status": t.status, "groupId": sid(t.group_id), "bookingId": sid(t.booking_id), "conf": t.conf} for t in TransportArrangement.objects.all()] if view_um else []

    S["supplierPayments"] = [{"id": sid(p.pk), "ref": p.ref, "supplierId": sid(p.supplier_id), "date": d(p.date), "amount": m(p.amount), "account": p.account.code,
                              "method": p.method, "txRef": p.tx_ref, "by": sid(p.by_id), "notes": p.notes}
                             for p in SupplierPayment.objects.select_related("account")] if can("supplier.view") else []
    S["expenses"] = [{"id": sid(e.pk), "ref": e.ref, "date": d(e.date), "cat": e.category, "desc": e.desc, "amount": m(e.amount), "method": e.method,
                      "account": e.account.code, "branch": sid(e.branch_id), "status": e.status, "by": sid(e.submitted_by_id), "supplierId": sid(e.supplier_id),
                      "approvedBy": e.approved_by, "attachment": sid(e.attachment_id), "attachmentName": e.attachment.original_name if e.attachment_id else "",
                      "rejectReason": e.reject_reason} for e in Expense.objects.select_related("account", "attachment")] if can("expense.view") else []
    S["refunds"] = [{"id": sid(r.pk), "ref": r.ref, "bookingId": sid(r.booking_id), "paymentId": sid(r.payment_id), "customerId": sid(r.booking.customer_id),
                     "requested": m(r.requested), "approved": m(r.approved), "cancelFee": m(r.cancel_fee), "fee": m(r.fee), "supplierCredit": m(r.supplier_credit),
                     "method": r.method, "reason": r.reason, "reqBy": r.requested_by, "apprBy": r.approved_by, "status": r.status, "date": d(r.date),
                     "completedOn": d(r.completed_on), "rejectReason": r.reject_reason, "history": r.history}
                    for r in Refund.objects.select_related("booking")] if can("refund.view") else []
    S["commissions"] = [{"id": sid(c.pk), "ref": c.ref, "kind": c.kind, "party": c.party, "partyId": sid(c.agent_id or c.employee_id or c.supplier_id),
                         "bookingId": sid(c.booking_id), "basis": c.basis, "amount": m(c.amount), "status": c.status, "date": d(c.date), "paidOn": d(c.paid_on)}
                        for c in Commission.objects.all()] if can("commission.view") else []
    S["commRules"] = [{"id": sid(r.pk), "kind": r.kind, "service": r.service, "basis": r.basis, "rate": m(r.rate)} for r in CommissionRule.objects.all()]

    view_ag = can("agent.view")
    S["agents"] = [{"id": sid(a.pk), "code": a.code, "name": a.name, "city": a.city, "limit": m(a.credit_limit), "opening": m(a.opening_balance), "wallet": m(a.wallet),
                    "status": a.status, "rate": m(a.commission_rate), "contact": a.contact, "joined": d(a.joined), "branch": sid(a.branch_id),
                    "balance": m(Decimal(str(agent_bal.get(sid(a.pk), 0))) + a.opening_balance)} for a in Agent.objects.all()] if (view_ag or view_bk) else []
    S["agentReqs"] = [{"id": sid(q.pk), "agentId": sid(q.agent_id), "service": q.service, "desc": q.desc, "pax": q.pax, "travelDate": d(q.travel_date),
                       "amount": m(q.amount), "cost": m(q.cost), "date": d(q.date), "status": q.status, "bookingId": sid(q.booking_id), "reason": q.reason}
                      for q in AgentRequest.objects.all()] if view_ag else []

    view_enq = can("enquiry.view")
    S["enquiries"] = [{"id": sid(e.pk), "ref": e.ref, "customerId": sid(e.customer_id), "lead": e.lead, "phone": e.phone, "service": e.service, "dest": e.dest,
                       "travelDate": d(e.travel_date), "value": m(e.value), "emp": sid(e.employee_id), "stage": e.stage, "source": e.source, "nextFollow": d(e.next_follow),
                       "created": d(e.created), "bookingId": sid(e.booking_id), "lostReason": e.lost_reason, "branch": sid(e.branch_id), "history": e.history}
                      for e in Enquiry.objects.all()] if view_enq else []
    S["quotes"] = [{"id": sid(q.pk), "ref": q.ref, "to": q.to, "title": q.title, "items": q.items, "total": m(q.total), "valid": d(q.valid_until), "terms": q.terms,
                    "enquiryId": sid(q.enquiry_id), "date": d(q.created)} for q in Quote.objects.all()] if view_enq else []
    S["comms"] = [{"id": sid(c.pk), "customerId": sid(c.customer_id), "at": dtl(c.at), "channel": c.channel, "dir": c.direction, "text": c.text, "by": c.by}
                  for c in Communication.objects.all()] if view_cust else []
    S["documents"] = [{"id": sid(x.pk), "type": x.type, "file": x.original_name, "customerId": sid(x.customer_id), "bookingId": sid(x.booking_id),
                       "uploaded": d(timezone.localtime(x.uploaded_at).date()), "expiry": d(x.expiry), "status": x.status, "uploadedBy": x.uploaded_by,
                       "size": x.size, "contentType": x.content_type} for x in Document.objects.all()] if view_cust else []

    view_j = can("journal.view") or can("cash.view")
    if view_j:
        lines = {}
        for ln in JournalLine.objects.select_related("account").order_by("id").values("entry_id", "account__code", "debit", "credit"):
            lines.setdefault(ln["entry_id"], []).append([ln["account__code"], m(ln["debit"]), m(ln["credit"])])
        matched = set(BankMatch.objects.values_list("entry_id", flat=True))
        S["journal"] = [{"id": sid(e.pk), "date": d(e.date), "ref": e.ref, "memo": e.memo, "src": e.source, "booking": sid(e.booking_id), "by": e.created_by,
                         "lines": lines.get(e.pk, [])} for e in JournalEntry.objects.all().order_by("date", "id")]
        S["bankRecon"] = {"statement": m(o.bank_statement_balance), "matched": {sid(i): True for i in matched}}
    else:
        S["journal"], S["bankRecon"] = [], {"statement": None, "matched": {}}
    S["periods"] = [{"id": sid(p.pk), "name": p.name, "from": d(p.start), "to": d(p.end), "status": p.status, "closedBy": p.closed_by, "closedOn": d(p.closed_on)}
                    for p in Period.objects.all()]
    S["closings"] = [{"id": sid(c.pk), "ref": c.ref, "date": d(c.date), "account": c.account.code, "branch": sid(c.account.branches.first().pk if c.account.branches.exists() else None),
                      "opening": m(c.opening), "receipts": m(c.receipts), "payments": m(c.payments), "expected": m(c.expected), "counted": m(c.counted),
                      "diff": m(c.diff), "status": c.status, "note": c.note, "by": c.by, "adjPosted": c.adj_posted}
                     for c in CashClosing.objects.select_related("account").order_by("-date", "-id")] if can("cash.view") else []
    S["audit"] = [{"id": sid(a.pk), "at": dtl(a.at), "user": a.user_name, "action": a.action, "module": a.module, "ref": a.ref, "prev": a.prev, "next": a.next,
                   "reason": a.reason, "sev": a.severity} for a in AuditLog.objects.all()[:800]] if can("settings.view") else \
        [{"id": sid(a.pk), "at": dtl(a.at), "user": a.user_name, "action": a.action, "module": a.module, "ref": a.ref, "prev": "", "next": "", "reason": "", "sev": a.severity}
         for a in AuditLog.objects.filter(user=user)[:100]]
    S["notifications"] = build_notifications(user, S, o)
    S["onboard"] = {"org": bool(o.setup_completed_at), "employee": Employee.objects.count() > 1, "accounts": JournalEntry.objects.filter(source__in=["Opening", "Manual journal"]).exists(),
                    "customer": Customer.objects.exists(), "booking": Booking.objects.exists(), "payment": Payment.objects.exists(), "dashboard": True}
    if can("settings.view"):
        docs = [p for p in settings.DOCUMENTS_ROOT.rglob("*") if p.is_file()]
        bks = list_backups()
        S["system"] = {"dataRoot": str(settings.DATA_ROOT), "dbPath": str(settings.DB_PATH), "dbSize": sum(f.stat().st_size for f in (settings.DB_PATH, Path(str(settings.DB_PATH) + "-wal")) if f.exists()),
                       "documentsDir": str(settings.DOCUMENTS_ROOT), "documentsCount": len(docs), "documentsBytes": sum(p.stat().st_size for p in docs),
                       "backupsDir": str(settings.BACKUP_ROOT), "backups": bks[:30], "lastBackup": bks[0]["at"] if bks else None,
                       "counts": {"customers": Customer.objects.count(), "bookings": Booking.objects.count(), "payments": Payment.objects.count(),
                                  "journal": JournalEntry.objects.count(), "documents": Document.objects.count()},
                       "health": ledger_health(S)}
        if settings.DEMO_MODE:  # don't expose the hosting server's file paths
            for k in ("dataRoot", "dbPath", "documentsDir", "backupsDir"):
                S["system"][k] = "Online demo server"
    return S


def _demo_info():
    if not settings.DEMO_MODE:
        return None
    from web.demo import next_reset
    nr = next_reset()
    return {"nextReset": nr.isoformat(timespec="minutes") if nr else None, "resetHours": settings.DEMO_RESET_HOURS}


def ledger_health(S):
    """Cross-checks control accounts against their sub-ledgers."""
    ar_ledger = ledger.account_balance("1100") if Account.objects.filter(code="1100").exists() else 0
    ar_sub = sum(Decimal(str(b["balance"])) for b in S["bookings"]) + sum((a.opening_balance for a in Agent.objects.all()), Decimal(0))
    ap_ledger = ledger.account_balance("2000") if Account.objects.filter(code="2000").exists() else 0
    ap_sub = sum(ledger.supplier_ledger(s)["balance"] for s in Supplier.objects.all())
    unbalanced = 0
    for e in JournalEntry.objects.annotate(dr=Sum("lines__debit"), cr=Sum("lines__credit")):
        if e.dr != e.cr:
            unbalanced += 1
    return {"arLedger": m(ar_ledger), "arSub": m(ar_sub), "apLedger": m(ap_ledger), "apSub": m(ap_sub), "unbalanced": unbalanced,
            "ok": unbalanced == 0 and Decimal(ar_ledger) == ar_sub and Decimal(ap_ledger) == ap_sub}


def build_notifications(user, S, o):
    """Live alerts computed from the data; read/unread state is stored per user."""
    today = timezone.localdate()
    N = []

    def n(key, cat, title, text, tone, route, params=None):
        if o.notification_prefs.get(cat, {}).get("app", 1):
            N.append({"id": key, "cat": cat, "title": title, "text": text, "tone": tone, "route": route, "params": params or {}, "at": today.isoformat() + "T08:00"})

    bk = S["bookings"]
    ov = [b for b in bk if b["payStatus"] == "Overdue"]
    if ov:
        n(f"overdue-{len(ov)}-{today}", "Payments", f"{len(ov)} customer payment{'s are' if len(ov) > 1 else ' is'} overdue", "Oldest: " + ov[-1]["ref"], "err", "bookings", {"preset": "bookings|pay=Overdue"})
    vm = [v for v in S["visas"] if any(x["status"] == "Missing" for x in v["docs"]) and v["status"] in ("New Enquiry", "Documents Pending", "Documents Verified", "Ready to Submit")]
    if vm:
        n(f"visadocs-{len(vm)}-{today}", "Visa Deadlines", f"{len(vm)} visa application{'s require' if len(vm) > 1 else ' requires'} documents", ", ".join(v["ref"] for v in vm[:3]), "warn", "visas", {"preset": "visas|docs=Missing"})
    vo = [v for v in S["visas"] if v["expected"] and v["expected"] < today.isoformat() and v["status"] in ("Submitted", "Processing", "Additional Information Required")]
    for v in vo[:5]:
        n(f"visaover-{v['id']}", "Visa Deadlines", f"{v['ref']}: expected decision date has passed", f"{v['country']} · expected {v['expected']}", "err", "visa", {"id": v["id"]})
    ra = [r for r in S["refunds"] if r["status"] == "Awaiting Approval"]
    if ra:
        n(f"refunds-{','.join(r['id'] for r in ra)}", "Payments", f"{len(ra)} refund{'s require' if len(ra) > 1 else ' requires'} approval", ra[0]["ref"], "warn", "refunds", {"preset": "refunds|status=Awaiting Approval"})
    wk = [b for b in bk if b["travelDate"] and today.isoformat() <= b["travelDate"] <= (today + dt.timedelta(days=7)).isoformat() and b["status"] in ("Confirmed", "Pending")]
    if wk:
        n(f"departures-{today}-{len(wk)}", "Travel Departures", f"{len(wk)} departure{'s' if len(wk) > 1 else ''} in the next 7 days", ", ".join(b["destination"] for b in wk[:3]), "info", "bookings", {"preset": "bookings|week=1"})
    dc = [c for c in S["closings"] if c["status"].startswith("Discrepancy")]
    if dc:
        n(f"cashdisc-{','.join(c['id'] for c in dc)}", "System Alerts", f"{len(dc)} cash closing discrepanc{'ies' if len(dc) > 1 else 'y'} to review", dc[0]["ref"], "err", "cashbank", {"tab": "closing"})
    pe = [e for e in S["expenses"] if e["status"] == "Pending"]
    if pe:
        n(f"expenses-{','.join(e['id'] for e in pe)}", "Payments", f"{len(pe)} expense{'s' if len(pe) > 1 else ''} waiting for approval", pe[0]["desc"], "warn", "expenses", {"preset": "expenses|status=Pending"})
    hp = [h for h in S["hotels"] if h["status"] == "Pending confirmation" and h["checkIn"] and h["checkIn"] >= today.isoformat()]
    if hp:
        n(f"hotels-{len(hp)}-{today}", "Booking Updates", f"{len(hp)} hotel reservation{'s' if len(hp) > 1 else ''} not yet confirmed", hp[0]["hotel"], "warn", "hotels")
    fu = [e for e in S["enquiries"] if e["nextFollow"] and e["nextFollow"] < today.isoformat() and e["stage"] not in ("Converted", "Lost")]
    if fu:
        n(f"followups-{today}-{len(fu)}", "Booking Updates", f"{len(fu)} enquiry follow-up{'s are' if len(fu) > 1 else ' is'} overdue", ", ".join(e["ref"] for e in fu[:3]), "warn", "enquiries")
    ar = [q for q in S["agentReqs"] if q["status"] == "Pending"]
    if ar:
        n(f"agentreq-{','.join(q['id'] for q in ar)}", "Booking Updates", f"{len(ar)} sub-agent booking request{'s' if len(ar) > 1 else ''} awaiting approval", "Credit checks run on approval", "info", "subagents", {"tab": "requests"})
    exp = [c for c in S["customers"] if c["passport"] and c["passport"]["expiry"] and c["passport"]["expiry"] < (today + dt.timedelta(days=180)).isoformat()]
    if exp:
        n(f"passports-{len(exp)}-{today:%Y%m}", "Visa Deadlines", f"{len(exp)} customer passport{'s expire' if len(exp) > 1 else ' expires'} within 6 months", ", ".join(c["name"] for c in exp[:3]), "warn", "customers")
    reads = dict(NotificationState.objects.filter(user=user, key__in=[x["id"] for x in N]).values_list("key", "read"))
    for x in N:
        x["read"] = reads.get(x["id"], False)
    return N
