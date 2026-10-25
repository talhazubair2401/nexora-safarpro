"""
Optional sample data for evaluating SafarPro (chosen on the first-run screen or with
`python manage.py load_sample_data`). Everything is created through the same business
actions the app uses, so the books balance exactly as they would with real entries.
All names, phone numbers and references are fictional.
"""
import datetime as dt
import random

from django.db import transaction
from django.utils import timezone

from accounts.models import Employee
from core.models import Branch, Organization
from crm.models import Customer, Enquiry
from finance import ledger
from operations.models import Agent, Booking, Departure, Supplier, Tour, UmrahGroup, UmrahPackage

from . import actions as A


@transaction.atomic
def load_sample_data(user):
    ctx = A.Ctx(user)
    R = random.Random(2026)
    today = timezone.localdate()
    ago = lambda n: today - dt.timedelta(days=n)
    org = Organization.get()
    main = ctx.emp.branch

    for code, name, city in (("ISB", "Islamabad Branch", "Islamabad"), ("KHI", "Karachi Branch", "Karachi")):
        if not Branch.objects.filter(code=code).exists():
            A.branch_create(ctx, {"code": code, "name": name, "city": city})
    br = {b.code: b for b in Branch.objects.all()}
    emps = {}
    for name, role, code in (("Sana Iqbal", "Accountant", main.code), ("Bilal Hussain", "Ticketing Officer", main.code), ("Mehwish Akhtar", "Visa Officer", "ISB"),
                             ("Kamran Shah", "Branch Manager", "ISB"), ("Nida Farooq", "Tour Operations Officer", main.code), ("Zain Abbas", "Receptionist", "KHI")):
        A.employee_save(ctx, {"name": name, "role": role, "branch": br[code].pk, "email": name.lower().replace(" ", ".") + "@example.com"})
        emps[role] = Employee.objects.get(name=name)
    sups = {}
    for name, cat, terms in (("Skyline Air Consolidators", "Airline / Consolidator", 7), ("Crescent Air Travel", "Airline / Consolidator", 15),
                             ("VisaLink Processing Services", "Visa Service Provider", 7), ("Al-Noor Umrah Services", "Umrah Package Supplier", 30),
                             ("Gulf Hotels Network", "Hotel", 15), ("Northern Wheels Transport", "Transport Provider", 7), ("Hunza Valley Tours", "Tour Operator", 15),
                             ("Bosphorus Travel DMC", "Tour Operator", 21)):
        A.supplier_save(ctx, {"name": name, "cat": cat, "terms": terms, "contact": "Reservations desk", "phone": "042-3555-0000"})
        sups[name] = Supplier.objects.get(name=name)

    # Opening balances (owner capital into cash and bank)
    opening = [{"acct": br[main.code].cash_account.code, "dr": 450000}, {"acct": br["ISB"].cash_account.code, "dr": 200000},
               {"acct": br["KHI"].cash_account.code, "dr": 180000}, {"acct": "1010", "dr": 18500000}, {"acct": "3000", "cr": 19330000}]
    ledger.post(ago(200), "JV-OPEN", "Opening balances brought forward", "Opening", [(l["acct"], l.get("dr", 0), l.get("cr", 0)) for l in opening], user)

    names = ["Ahmed Raza", "Hamza Ali", "Ayesha Malik", "Fatima Noor", "Usman Tariq", "Sara Javed", "Imran Qureshi", "Hina Aslam", "Faisal Mehmood",
             "Zainab Hassan", "Omar Siddiqui", "Mariam Baig", "Adeel Chaudhry", "Saima Rauf", "Waqas Ahmed", "Nadia Sheikh", "Asad Butt", "Rabia Khalid"]
    custs = []
    for i, n in enumerate(names):
        city, b = [("Lahore", main.code), ("Islamabad", "ISB"), ("Karachi", "KHI")][i % 3]
        A.customer_save(ctx, {"name": n, "phone": f"0300-555{1001 + i * 7:04d}"[:12], "type": "Individual", "country": "Pakistan", "city": city,
                              "passportNo": f"DM{1000000 + i * 37:07d}" if i % 4 != 3 else "", "passportExpiry": (today + dt.timedelta(days=[480, 900, 150, 0, 60, 700][i % 6] or 400)).isoformat() if i % 4 != 3 else "",
                              "branch": br[b].pk, "email": n.lower().replace(" ", ".") + "@example.com"})
        custs.append(Customer.objects.get(name=n))
    for n, t in (("Ravi Textiles (Pvt) Ltd", "Corporate"), ("Al-Falah Masjid Committee", "Group Organizer")):
        A.customer_save(ctx, {"name": n, "phone": f"0321-555{7000 + len(custs):04d}", "type": t, "country": "Pakistan", "city": "Lahore", "branch": main.pk})
        custs.append(Customer.objects.get(name=n))

    def booking(c, service, dest, travel, price, cost, sup, emp, days_ago, pay=1.0, pax=1, **kw):
        b = A.new_booking(ctx, status="Confirmed", customer=c, service=service, destination=dest, travel_date=travel, pax=pax, passengers=[c.name],
                          price=price, cost=cost, supplier=sup, employee=emp, created=ago(days_ago), posted_on=ago(days_ago), **kw)
        if pay:
            amt = round(price * pay / 1000) * 1000 if pay < 1 else price
            A.record_payment(ctx, b, amt, ago(max(0, days_ago - 1)), R.choice(["Cash", "Bank Transfer", "Card"]), f"TRX-DEMO-{b.pk:05d}" if True else "", "")
        return b

    # Six months of history: completed trips paid in full, suppliers settled, monthly overheads.
    # Gives the dashboard and reports a realistic trend instead of a single busy month.
    month_starts = []
    for back in range(6, 0, -1):
        y, m = today.year, today.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        month_starts.append(dt.date(y, m, 1))
    hist_mix = [("Air Ticket", "LHE → DXB → LHE", 165000, 0.09, "Skyline Air Consolidators", 1), ("Air Ticket", "ISB → LHR → ISB", 395000, 0.08, "Crescent Air Travel", 1),
                ("Air Ticket", "KHI → JED → KHI", 248000, 0.1, "Skyline Air Consolidators", 1), ("Tour", "Hunza", 68000, 0.22, "Hunza Valley Tours", 3),
                ("Tour", "Istanbul", 385000, 0.16, "Bosphorus Travel DMC", 2), ("Hotel", "Makkah — 7 nights", 210000, 0.12, "Gulf Hotels Network", 1),
                ("Umrah", "Makkah & Madinah", 275000, 0.11, "Al-Noor Umrah Services", 6), ("Transport", "Skardu — 5-day coaster", 95000, 0.18, "Northern Wheels Transport", 1)]
    for mi, ms in enumerate(month_starts):
        growth = 1.15 + mi * 0.08
        sup_due = {}
        for k, (svc, dest, unit, margin, supn, pax) in enumerate(hist_mix):
            for rep in range(3 if svc in ("Air Ticket", "Tour") else 1):
                day = min(2 + (k * 3 + rep * 9 + R.randint(0, 4)) % 25, 27)
                when = ms + dt.timedelta(days=day)
                if when >= today:
                    continue
                n = max(1, round(pax * growth * R.uniform(0.85, 1.2)))
                price = round(unit * n * R.uniform(0.92, 1.08) / 1000) * 1000
                cost = round(price * (1 - margin) / 1000) * 1000
                c = custs[R.randrange(0, len(custs))]
                emp = emps["Ticketing Officer"] if svc == "Air Ticket" else emps["Tour Operations Officer"] if svc in ("Tour", "Transport") else ctx.emp
                b = A.new_booking(ctx, status="Completed", customer=c, service=svc, destination=dest, travel_date=min(when + dt.timedelta(days=R.randint(5, 20)), today - dt.timedelta(days=1)),
                                  pax=n, passengers=[c.name], price=price, cost=cost, supplier=sups[supn], employee=emp, created=when, posted_on=when)
                A.record_payment(ctx, b, price, min(when + dt.timedelta(days=R.randint(0, 3)), today), R.choice(["Cash", "Bank Transfer", "Card"]), f"TRX-HIST-{b.pk:05d}", "")
                sup_due[supn] = sup_due.get(supn, 0) + cost
        pay_day = min(ms + dt.timedelta(days=27), today)
        for supn, amt in sup_due.items():
            A.supplier_payment(ctx, {"supplierId": sups[supn].pk, "amount": int(amt), "date": pay_day.isoformat(), "account": "1010", "method": "Bank Transfer", "txRef": f"IBFT-{ms:%y%m}-{sups[supn].pk:03d}"})
        for day, cat, desc, amt, cash in ((1, "Salaries", "Staff salaries", 385000, False), (3, "Office Rent", "Office rent — main branch", 120000, False),
                                          (12, "Utilities", "Electricity & internet", R.randint(24, 34) * 1000, True), (15, "Marketing", "Facebook & Instagram ads", R.randint(30, 48) * 1000, False),
                                          (20, "Software", "Email & cloud backup", 12500, False)):
            d0 = ms + dt.timedelta(days=day)
            if d0 >= today:
                continue
            A.expense_create(ctx, {"date": d0.isoformat(), "cat": cat, "desc": desc, "amount": amt, "method": "Cash" if cash else "Bank Transfer",
                                   "account": br[main.code].cash_account.code if cash else "1010", "branch": main.pk})
    # Current month salaries
    if today.day > 1:
        A.expense_create(ctx, {"date": today.replace(day=1).isoformat(), "cat": "Salaries", "desc": "Staff salaries", "amount": 385000, "method": "Bank Transfer", "account": "1010", "branch": main.pk})

    tk = emps["Ticketing Officer"]
    air = [(0, "Emirates", "LHE → DXB → LHE", 20, 172000, 155000, 40, 1.0), (4, "Qatar Airways", "KHI → LHR → KHI", 25, 415000, 378000, 12, 0.5),
           (10, "Turkish Airlines", "ISB → IST → ISB", 5, 314000, 281000, 22, 1.0), (1, "Saudia", "LHE → JED → LHE", 38, 268000, 237000, 4, 0),
           (19, "PIA", "LHE → KHI", 3, 29000, 24500, 18, 0)]
    for ci, airline, route, ahead, price, cost, back, pay in air:
        booking(custs[ci], "Air Ticket", route, today + dt.timedelta(days=ahead), price, cost, sups["Skyline Air Consolidators"], tk, back, pay, airline=airline)

    # Tours with departures and seat sales
    tours = [("Hunza & Khunjerab Explorer", "Hunza", "Domestic", 6, 68000, 52000, "Hunza Valley Tours", [(6, 20), (20, 20)]),
             ("Skardu & Shangrila Escape", "Skardu", "Domestic", 7, 82000, 63000, "Hunza Valley Tours", [(13, 18)]),
             ("Istanbul & Cappadocia Discovery", "Istanbul", "International", 8, 385000, 322000, "Bosphorus Travel DMC", [(27, 16)]),
             ("Dubai City & Desert Safari", "Dubai", "International", 5, 189000, 158000, "Gulf Hotels Network", [(33, 20)])]
    for name, dest, region, days, price, cost, sup, deps in tours:
        A.tour_save(ctx, {"name": name, "dest": dest, "region": region, "days": days, "price": price, "cost": cost, "sup": sups[sup].pk, "transport": "Coaster / flights as listed",
                          "hotel": "3–4★ hotels", "itin": "\n".join(f"Day {i + 1} sightseeing" for i in range(days)), "inc": "Transport\nHotels\nBreakfast",
                          "exc": "Lunch\nPersonal expenses", "policy": "Full refund up to 15 days before departure. 50% refund 7–14 days before. No refund within 7 days."})
        t = Tour.objects.get(name=name)
        for ahead, cap in deps:
            A.tour_departure(ctx, {"id": t.pk, "date": (today + dt.timedelta(days=ahead)).isoformat(), "capacity": cap})
        for dep in t.departures.all():
            for k in range(R.randint(2, 3)):
                pax = R.randint(2, 4)
                c = custs[R.randrange(0, 18)]
                booking(c, "Tour", dest, dep.date, price * pax, cost * pax, sups[sup], emps["Tour Operations Officer"], R.randint(3, 30), R.choice([1.0, 0.5, 0.3, 0]), pax, departure=dep)

    # Visa applications through the workflow
    for ci, country, typ, emb, svc, stage in ((2, "United Kingdom", "Standard Visitor", 38500, 15000, "Processing"), (5, "Germany (Schengen)", "Short-stay Tourist", 26000, 18000, "Documents Pending"),
                                             (8, "Canada", "Visitor Visa", 30500, 20000, "Submitted"), (11, "United Arab Emirates", "30-day e-Visa", 21500, 6500, "Approved")):
        r = A.visa_create(ctx, {"customerId": custs[ci].pk, "country": country, "type": typ, "travel": (today + dt.timedelta(days=45)).isoformat(), "emb": emb, "svc": svc,
                                "officer": emps["Visa Officer"].pk, "status": "Documents Pending", "supplierId": sups["VisaLink Processing Services"].pk})
        from operations.models import VisaApplication
        va = VisaApplication.objects.get(pk=int(r["id"]))
        if stage != "Documents Pending":
            for doc in va.docs:
                doc["status"] = "Verified"
            va.save()
            for s in ("Documents Verified", "Ready to Submit", "Submitted", "Processing", "Approved"):
                A.visa_status(ctx, {"id": va.pk, "status": s})
                if s == stage:
                    break
            A.record_payment(ctx, va.booking, va.booking.price, today, "Cash")

    # Umrah
    A.umrah_package(ctx, {"name": "Economy Umrah — 15 Days", "days": 15, "makkah": "Dar Al Safa Hotel (900 m)", "madinah": "Rawdat Al Noor Hotel (650 m)", "transport": "Shared AC coach",
                          "room": "Quad sharing", "flight": "Saudia", "cost": 245000, "sell": 275000, "capacity": 45, "inc": "Return airfare\nVisa\nHotels\nZiyarat", "exc": "Meals"})
    A.umrah_package(ctx, {"name": "Standard Umrah — 21 Days", "days": 21, "makkah": "Ajyad View Residency (450 m)", "madinah": "Bab Al Salam Suites (300 m)", "transport": "Private coach",
                          "room": "Quad / Triple", "flight": "Saudia", "cost": 310000, "sell": 349000, "capacity": 40, "inc": "Return airfare\nVisa\nHotels\nBreakfast & dinner", "exc": "Lunch"})
    pkg = UmrahPackage.objects.get(name__startswith="Standard")
    pilgrims = ["Muhammad Aslam", "Shamim Akhtar", "Abdul Rehman", "Naseem Bibi", "Ghulam Mustafa", "Rashida Begum", "Tahir Mehmood", "Kausar Parveen", "Muhammad Saleem", "Zubaida Khatoon", "Nasir Iqbal", "Parveen Akhtar"]
    A.umrah_book(ctx, {"pkgId": pkg.pk, "groupId": "new", "gname": "Al-Falah Group", "gdep": (today + dt.timedelta(days=19)).isoformat(), "customerId": custs[-1].pk,
                       "emp": ctx.emp.pk, "pilgrims": "\n".join(pilgrims)})
    gb = Booking.objects.filter(service="Umrah").latest("id")
    A.booking_confirm(ctx, {"id": gb.pk})
    A.record_payment(ctx, gb, 2500000, today, "Bank Transfer", "IBFT-DEMO-0001")
    for i, p in enumerate(gb.pilgrims.all()):
        p.passport_status = "Missing" if i == 3 else "Valid"
        p.visa_status = "Approved" if i not in (3, 7) else "Pending documents"
        p.room = f"Q-{i // 4 + 1}" if i != 10 else ""
        p.payment_status = "Paid" if i % 5 else "Partial"
        p.emergency = f"Relative · 0300-555{4000 + i:04d}"
        p.save()

    # Cancellation with refund, and a refund awaiting approval
    paid_tours = [b for b in Booking.objects.filter(service="Tour", status="Confirmed") if ledger.figures(b)["balance"] == 0 and b.travel_date > today]
    if paid_tours:
        b = paid_tours[0]
        fee = round(b.price / 10 / 1000) * 1000
        A.refund_request(ctx, {"bookingId": b.pk, "cancelFee": fee, "fee": 0, "requested": int(b.price - fee), "method": "Bank Transfer", "reason": "Family emergency (sample)"})
        from finance.models import Refund
        r = Refund.objects.latest("id")
        A.refund_step(ctx, {"id": r.pk})
        A.refund_step(ctx, {"id": r.pk})
    if len(paid_tours) > 1:
        b = paid_tours[1]
        fee = round(b.price / 2 / 1000) * 1000
        A.refund_request(ctx, {"bookingId": b.pk, "cancelFee": fee, "fee": 1000, "requested": int(b.price - fee - 1000), "method": "Cash", "reason": "Cancelled 5 days before (sample)"})
        from finance.models import Refund
        r = Refund.objects.latest("id")
        A.refund_step(ctx, {"id": r.pk}); A.refund_step(ctx, {"id": r.pk})
        A.refund_approve(ctx, {"id": r.pk, "approved": int(r.requested), "supplierCredit": 0})
        A.refund_complete(ctx, {"id": r.pk})

    # Expenses
    for days, cat, desc, amt, acct in ((24, "Office Rent", "Office rent — main branch", 120000, "1010"), (20, "Utilities", "Electricity & internet", 28500, br[main.code].cash_account.code),
                                       (15, "Marketing", "Facebook & Instagram ads", 45000, "1010"), (8, "Software", "Email & cloud backup", 12500, "1010"),
                                       (3, "Other", "Office refreshments & stationery", 7400, br[main.code].cash_account.code)):
        A.expense_create(ctx, {"date": ago(days).isoformat(), "cat": cat, "desc": desc, "amount": amt, "method": "Cash" if acct != "1010" else "Bank Transfer", "account": acct, "branch": main.pk})

    from finance.models import Expense
    from django.db.models import Q as _Q
    for e in Expense.objects.filter(status="Pending").filter(_Q(date__lt=today.replace(day=1)) | _Q(desc__icontains="rent") | _Q(category="Salaries")):
        A.expense_decide(ctx, {"id": e.pk, "decision": "approve"})

    # Supplier payments
    for s in (sups["Skyline Air Consolidators"], sups["Hunza Valley Tours"], sups["Al-Noor Umrah Services"]):
        bal = ledger.supplier_ledger(s)["balance"]
        if bal > 0:
            A.supplier_payment(ctx, {"supplierId": s.pk, "amount": int(bal / 2 // 1000 * 1000) or int(bal), "date": today.isoformat(), "account": "1010", "method": "Bank Transfer", "txRef": f"IBFT-DEMO-{s.pk:04d}"})

    # Sub-agent and a request
    A.agent_save(ctx, {"name": "Zamzam Travel Desk", "city": "Gujranwala", "contact": "0300-5556001", "limit": 600000, "rate": 1.5, "opening": 145000})
    a = Agent.objects.latest("id")
    A.agent_approve(ctx, {"id": a.pk})
    A.agent_req_create(ctx, {"agentId": a.pk, "service": "Air Ticket", "desc": "GRW → JED · 3 pax · Saudia", "pax": 3, "travelDate": (today + dt.timedelta(days=30)).isoformat(),
                             "amount": 390000, "cost": 366000, "supplierId": sups["Crescent Air Travel"].pk})
    A.agent_req_create(ctx, {"agentId": a.pk, "service": "Tour", "desc": "Dubai City & Desert Safari · 4 pax", "pax": 4, "travelDate": (today + dt.timedelta(days=33)).isoformat(),
                             "amount": 756000, "cost": 632000, "supplierId": sups["Gulf Hotels Network"].pk})

    # Enquiries
    for who, service, dest, val, stage in ((custs[6], "Air Ticket", "Toronto (YYZ)", 420000, "Contacted"), (custs[9], "Tour", "Hunza", 136000, "Quotation Sent"),
                                           (None, "Umrah", "Makkah & Madinah", 540000, "New"), (custs[12], "Visa", "United Kingdom", 55000, "Follow-up Required")):
        payload = {"who": "existing" if who else "lead", "customerId": who.pk if who else "", "lead": "Kashif Mehmood", "phone": "0301-5559911", "service": service, "dest": dest,
                   "travelDate": (today + dt.timedelta(days=40)).isoformat(), "value": val, "emp": ctx.emp.pk, "source": "WhatsApp", "nextFollow": (today + dt.timedelta(days=1)).isoformat()}
        r = A.enquiry_save(ctx, payload)
        if stage != "New":
            A.enquiry_stage(ctx, {"id": r["id"], "stage": stage})
    org.sample_data = True
    org.save(update_fields=["sample_data"])
