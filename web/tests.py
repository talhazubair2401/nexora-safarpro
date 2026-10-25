"""
Automated tests for Nexora SafarPro: financial accuracy, permissions, persistence,
documents, backups and idempotency. Run with:  python manage.py test
"""
import datetime as dt
import json
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Sum
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import Employee
from core.models import Branch
from core.setup import initialize
from crm.models import Customer, Document
from finance import ledger
from finance.models import JournalEntry, JournalLine, Payment, Refund
from operations.models import Booking, Supplier

PW = "Str0ng!Pass2026"
TODAY = timezone.localdate()


class Base(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._docs = tempfile.mkdtemp()
        cls._bk = tempfile.mkdtemp()
        cls._ov = override_settings(DOCUMENTS_ROOT=Path(cls._docs), BACKUP_ROOT=Path(cls._bk))
        cls._ov.enable()

    @classmethod
    def tearDownClass(cls):
        cls._ov.disable()
        shutil.rmtree(cls._docs, ignore_errors=True)
        shutil.rmtree(cls._bk, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.admin = initialize(org_name="Test Travels", city="Lahore", branch_name="Lahore Main", branch_code="LHR",
                                admin_name="Admin User", username="admin", password=PW)
        self.c = Client()
        self.c.login(username="admin", password=PW)
        self.branch = Branch.objects.get(code="LHR")
        self.act("supplier.save", {"name": "Sky Consolidators", "cat": "Airline / Consolidator", "terms": 7})
        self.sup = Supplier.objects.get()
        self.act("customer.save", {"name": "Ahmed Raza", "phone": "0300-5551001", "type": "Individual", "country": "Pakistan", "city": "Lahore"})
        self.cust = Customer.objects.get()
        # opening cash so refunds/supplier payments can be paid
        self.act("journal.create", {"date": TODAY.isoformat(), "memo": "Opening", "lines": [
            {"acct": self.branch.cash_account.code, "dr": 500000}, {"acct": "1010", "dr": 1000000}, {"acct": "3000", "cr": 1500000}]})

    def act(self, name, data, client=None, status=200, file=None):
        c = client or self.c
        if file:
            r = c.post(f"/api/action/{name}", {"payload": json.dumps(data), "file": file})
        else:
            r = c.post(f"/api/action/{name}", json.dumps(data), content_type="application/json")
        j = r.json()
        self.assertEqual(r.status_code, status, j)
        return j

    def booking(self, price=100000, cost=80000, status="Confirmed"):
        j = self.act("booking.create", {"customerId": self.cust.pk, "service": "Air Ticket", "destination": "LHE → DXB",
                                        "travelDate": (TODAY + dt.timedelta(days=20)).isoformat(), "pax": 1, "price": price, "cost": cost,
                                        "supplierId": self.sup.pk, "status": status, "emp": self.admin.employee.pk})
        return Booking.objects.get(pk=int(j["result"]["id"]))

    def assert_books_balance(self):
        t = JournalLine.objects.aggregate(d=Sum("debit"), c=Sum("credit"))
        self.assertEqual(t["d"], t["c"])
        for e in JournalEntry.objects.all():
            s = e.lines.aggregate(d=Sum("debit"), c=Sum("credit"))
            self.assertEqual(s["d"], s["c"], e.ref)

    def ar_consistent(self):
        sub = sum((ledger.figures(b)["balance"] for b in Booking.objects.all()), Decimal(0))
        self.assertEqual(ledger.account_balance("1100"), sub)

    def ap_consistent(self):
        sub = sum((ledger.supplier_ledger(s)["balance"] for s in Supplier.objects.all()), Decimal(0))
        self.assertEqual(ledger.account_balance("2000"), sub)


class FinanceTests(Base):
    def test_confirm_posts_invoice_and_cost(self):
        b = self.booking()
        self.assertEqual(ledger.account_balance("1100"), Decimal("100000"))
        self.assertEqual(ledger.account_balance("4000"), Decimal("100000"))
        self.assertEqual(ledger.account_balance("5000"), Decimal("80000"))
        self.assertEqual(ledger.account_balance("2000"), Decimal("80000"))
        self.assert_books_balance()

    def test_pending_booking_not_invoiced(self):
        b = self.booking(status="Pending")
        self.assertIsNone(b.posted_on)
        self.assertEqual(ledger.account_balance("4000"), 0)

    def test_partial_payment_and_balance(self):
        b = self.booking()
        j = self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 40000, "_key": "k1"})
        f = ledger.figures(b)
        self.assertEqual(f["paid"], 40000)
        self.assertEqual(f["balance"], 60000)
        self.assertEqual(f["pay_status"], "Partially Paid")
        p = Payment.objects.get(ref=j["result"]["ref"])
        self.assertEqual(p.prev_balance, 100000)
        self.assertEqual(p.new_balance, 60000)
        self.ar_consistent()
        self.assert_books_balance()

    def test_overpayment_rejected(self):
        b = self.booking()
        j = self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 100001}, status=400)
        self.assertIn("amount", j["errors"])
        self.assertEqual(Payment.objects.count(), 0)

    def test_invalid_amounts_rejected(self):
        b = self.booking()
        for amt in (-5, 0, "abc", 10.5):
            j = self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": amt}, status=400)
            self.assertIn("amount", j["errors"])
        self.assertEqual(Payment.objects.count(), 0)

    def test_future_date_rejected(self):
        b = self.booking()
        self.act("payment.create", {"bookingId": b.pk, "date": (TODAY + dt.timedelta(days=3)).isoformat(), "method": "Cash", "amount": 100}, status=400)

    def test_duplicate_submission_is_idempotent(self):
        b = self.booking()
        data = {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 10000, "_key": "same-key"}
        self.act("payment.create", data)
        j = self.act("payment.create", dict(data))
        self.assertTrue(j.get("duplicate"))
        self.assertEqual(Payment.objects.count(), 1)

    def test_duplicate_bank_reference_rejected(self):
        b = self.booking()
        self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Bank Transfer", "amount": 1000, "txRef": "IBFT-1"})
        j = self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Bank Transfer", "amount": 1000, "txRef": "ibft-1"}, status=400)
        self.assertIn("txRef", j["errors"])

    def test_receipt_numbers_unique_and_sequential(self):
        b = self.booking()
        refs = [self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 1000})["result"]["ref"] for _ in range(3)]
        self.assertEqual(len(set(refs)), 3)
        self.assertEqual(refs, sorted(refs))

    def test_reversal_keeps_history_and_restores_balance(self):
        b = self.booking()
        pid = self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 30000})["result"]["id"]
        self.act("payment.reverse", {"id": pid, "reason": "Duplicate entry"})
        p = Payment.objects.get(pk=pid)
        self.assertEqual(p.status, "Reversed")
        self.assertEqual(ledger.figures(b)["balance"], 100000)
        self.assertEqual(JournalEntry.objects.filter(source="Reversal").count(), 1)
        self.act("payment.reverse", {"id": pid, "reason": "again"}, status=400)
        self.assert_books_balance()

    def test_cancellation_reduces_revenue_not_original_price(self):
        b = self.booking()
        self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 100000})
        self.act("booking.cancel", {"id": b.pk, "fee": 10000, "supplierCredit": 70000, "reason": "Customer changed plans"})
        p = ledger
        # Net revenue = 100,000 invoiced − 90,000 reversed = 10,000 fee kept
        net_rev = p.account_balance("4000") + p.account_balance("4090")
        self.assertEqual(net_rev, Decimal("10000"))
        # Net direct cost = 80,000 − 70,000 supplier credit
        self.assertEqual(p.account_balance("5000"), Decimal("10000"))
        self.assertEqual(p.account_balance("2000"), Decimal("10000"))
        f = p.figures(Booking.objects.get(pk=b.pk))
        self.assertEqual(f["balance"], Decimal("-90000"))  # credit due to customer
        self.ar_consistent()
        self.ap_consistent()
        self.assert_books_balance()

    def test_refund_flow_pays_once_and_zeroes_balance(self):
        b = self.booking()
        self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 100000})
        self.act("refund.request", {"bookingId": b.pk, "cancelFee": 15000, "fee": 1000, "requested": 84000, "method": "Cash", "reason": "Visa refused"})
        r = Refund.objects.get()
        self.act("refund.step", {"id": r.pk})
        self.act("refund.step", {"id": r.pk})
        self.act("refund.approve", {"id": r.pk, "approved": 84000, "supplierCredit": 80000})
        cash_before = ledger.account_balance(self.branch.cash_account.code)
        self.act("refund.complete", {"id": r.pk})
        self.act("refund.complete", {"id": r.pk}, status=400)  # second click: no second payout
        self.assertEqual(JournalEntry.objects.filter(source="Refund", ref=r.ref).count(), 1)
        self.assertEqual(ledger.account_balance(self.branch.cash_account.code), cash_before - 84000)
        b.refresh_from_db()
        self.assertEqual(b.status, "Refunded")
        self.assertEqual(ledger.figures(b)["balance"], 0)
        # P&L: kept 15,000 cancellation + 1,000 fee; cost fully credited
        rev = sum(ledger.account_balance(c) for c in ("4000", "4040", "4090"))
        self.assertEqual(rev, Decimal("16000"))
        self.assertEqual(ledger.account_balance("5000"), 0)
        self.ar_consistent()
        self.ap_consistent()
        self.assert_books_balance()

    def test_refund_cannot_exceed_paid(self):
        b = self.booking()
        self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 20000})
        j = self.act("refund.request", {"bookingId": b.pk, "cancelFee": 5000, "fee": 0, "requested": 20000, "method": "Cash", "reason": "x"}, status=400)
        self.assertIn("requested", j["errors"])

    def test_cost_adjustment_posts_difference(self):
        b = self.booking()
        self.act("booking.cost", {"id": b.pk, "cost": 85000, "reason": "Fare increase"})
        self.assertEqual(ledger.account_balance("5000"), 85000)
        self.assertEqual(ledger.account_balance("2000"), 85000)
        self.ap_consistent()
        self.assert_books_balance()

    def test_supplier_payment_cannot_exceed_payable(self):
        self.booking()
        self.act("supplierPayment.create", {"supplierId": self.sup.pk, "amount": 90000, "date": TODAY.isoformat(), "account": "1010", "method": "Bank Transfer"}, status=400)
        self.act("supplierPayment.create", {"supplierId": self.sup.pk, "amount": 50000, "date": TODAY.isoformat(), "account": "1010", "method": "Bank Transfer"})
        self.assertEqual(ledger.supplier_ledger(self.sup)["balance"], 30000)
        self.ap_consistent()

    def test_expense_approval_limit(self):
        self.act("expense.create", {"date": TODAY.isoformat(), "cat": "Utilities", "desc": "Electricity", "amount": 5000, "method": "Cash", "account": self.branch.cash_account.code, "branch": self.branch.pk})
        self.act("expense.create", {"date": TODAY.isoformat(), "cat": "Office Rent", "desc": "Rent", "amount": 120000, "method": "Bank Transfer", "account": "1010", "branch": self.branch.pk})
        self.assertEqual(ledger.account_balance("6020"), 5000)
        self.assertEqual(ledger.account_balance("6000"), 0)  # pending, not posted

    def test_unbalanced_and_control_journals_rejected(self):
        self.act("journal.create", {"date": TODAY.isoformat(), "memo": "bad", "lines": [{"acct": "6090", "dr": 100}, {"acct": "1010", "cr": 90}]}, status=400)
        self.act("journal.create", {"date": TODAY.isoformat(), "memo": "bad", "lines": [{"acct": "1100", "dr": 100}, {"acct": "1010", "cr": 100}]}, status=400)

    def test_closed_period_blocks_postings(self):
        from finance.models import Period
        Period.objects.create(name="Old", start=TODAY - dt.timedelta(days=60), end=TODAY - dt.timedelta(days=30), status="Closed")
        b = self.booking()
        j = self.act("payment.create", {"bookingId": b.pk, "date": (TODAY - dt.timedelta(days=40)).isoformat(), "method": "Cash", "amount": 100}, status=400)
        self.assertIn("closed", j["message"].lower())

    def test_tour_capacity_enforced(self):
        self.act("tour.save", {"name": "Hunza", "dest": "Hunza", "region": "Domestic", "days": 5, "price": 50000, "cost": 40000, "itin": "Day 1", "policy": "Policy"})
        from operations.models import Departure, Tour
        t = Tour.objects.get()
        self.act("tour.departure", {"id": t.pk, "date": (TODAY + dt.timedelta(days=10)).isoformat(), "capacity": 3})
        d = Departure.objects.get()
        base = {"customerId": self.cust.pk, "service": "Tour", "depId": d.pk, "destination": "Hunza", "travelDate": d.date.isoformat(), "price": 100000, "cost": 80000, "supplierId": self.sup.pk, "status": "Confirmed", "emp": self.admin.employee.pk}
        self.act("booking.create", dict(base, pax=2))
        j = self.act("booking.create", dict(base, pax=2), status=400)
        self.assertIn("pax", j["errors"])

    def test_agent_credit_limit(self):
        self.act("agent.save", {"name": "Agent A", "city": "Sialkot", "contact": "0300-5550000", "limit": 100000, "rate": 1, "opening": 60000})
        from operations.models import Agent, AgentRequest
        a = Agent.objects.get()
        self.act("agent.approve", {"id": a.pk})
        self.act("agentReq.create", {"agentId": a.pk, "service": "Air Ticket", "desc": "Trip", "pax": 1, "travelDate": (TODAY + dt.timedelta(days=9)).isoformat(), "amount": 50000, "cost": 45000, "supplierId": self.sup.pk})
        j = self.act("agentReq.decide", {"id": AgentRequest.objects.get().pk, "decision": "approve"}, status=400)
        self.assertIn("Credit limit", j["message"])
        self.ar_consistent_with_agents()

    def ar_consistent_with_agents(self):
        from operations.models import Agent
        sub = sum((ledger.figures(b)["balance"] for b in Booking.objects.all()), Decimal(0)) + sum((a.opening_balance for a in Agent.objects.all()), Decimal(0))
        self.assertEqual(ledger.account_balance("1100"), sub)

    def test_state_health_check_ok(self):
        b = self.booking()
        self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Card", "amount": 50000, "txRef": "C1"})
        s = self.c.get("/api/state").json()["state"]
        self.assertTrue(s["system"]["health"]["ok"], s["system"]["health"])
        bk = [x for x in s["bookings"] if x["id"] == str(b.pk)][0]
        self.assertEqual(bk["balance"], 50000)


class SecurityTests(Base):
    def make_user(self, role, username):
        self.act("employee.save", {"name": role + " Person", "role": role, "branch": self.branch.pk, "username": username, "password": PW})
        c = Client()
        self.assertTrue(c.login(username=username, password=PW))
        return c

    def test_anonymous_cannot_read_or_write(self):
        anon = Client()
        self.assertEqual(anon.get("/api/state").status_code, 401)
        r = anon.post("/api/action/customer.save", "{}", content_type="application/json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(anon.get("/").status_code, 302)

    def test_receptionist_cannot_touch_finance(self):
        rc = self.make_user("Receptionist", "rec")
        b = self.booking()
        self.act("payment.create", {"bookingId": b.pk, "date": TODAY.isoformat(), "method": "Cash", "amount": 10}, client=rc, status=403)
        self.act("journal.create", {"date": TODAY.isoformat(), "memo": "x", "lines": []}, client=rc, status=403)
        self.act("employee.save", {"name": "Hacker", "role": "Administrator", "branch": self.branch.pk}, client=rc, status=403)
        s = rc.get("/api/state").json()["state"]
        self.assertEqual(s["journal"], [])
        self.assertEqual(s["payments"], [])
        self.assertNotIn("system", s)
        self.assertNotIn("email", s["employees"][0])
        # but can create customers
        self.act("customer.save", {"name": "Walk In", "phone": "0333-5552222", "type": "Individual", "country": "Pakistan", "city": "Lahore"}, client=rc)

    def test_accountant_cannot_manage_users(self):
        ac = self.make_user("Accountant", "acc")
        self.act("employee.role", {"id": self.admin.employee.pk, "role": "Receptionist", "branch": self.branch.pk, "reason": "x"}, client=ac, status=403)
        self.act("settings.save", {"org.name": "Hacked"}, client=ac, status=403)

    def test_suspended_user_is_locked_out(self):
        rc = self.make_user("Receptionist", "rec2")
        emp = Employee.objects.get(user__username="rec2")
        self.act("employee.status", {"id": emp.pk, "reason": "Left the company"})
        self.assertEqual(rc.get("/api/state").status_code, 401)
        self.assertFalse(Client().login(username="rec2", password=PW) and Client().post("/login/", {"username": "rec2", "password": PW}).status_code == 302)

    def test_csrf_enforced(self):
        c = Client(enforce_csrf_checks=True)
        c.login(username="admin", password=PW)
        r = c.post("/api/action/customer.save", json.dumps({"name": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_password_is_hashed(self):
        from django.contrib.auth.models import User
        self.assertNotIn(PW, User.objects.get(username="admin").password)
        self.assertTrue(User.objects.get(username="admin").password.startswith("pbkdf2_"))

    def test_login_lockout(self):
        c = Client()
        for _ in range(5):
            c.post("/login/", {"username": "admin", "password": "wrong"})
        r = c.post("/login/", {"username": "admin", "password": PW})
        self.assertContains(r, "Too many failed attempts")

    def test_setup_only_once(self):
        r = Client().get("/setup/")
        self.assertEqual(r.status_code, 302)


class DocumentAndBackupTests(Base):
    def test_document_upload_persists_and_is_protected(self):
        pdf = SimpleUploadedFile("passport.pdf", b"%PDF-1.4 test content", content_type="application/pdf")
        j = self.act("document.upload", {"type": "Passport", "customerId": self.cust.pk}, file=pdf)
        doc = Document.objects.get(pk=int(j["result"]["id"]))
        self.assertTrue((settings.DOCUMENTS_ROOT / doc.stored_name).exists())
        self.assertNotIn("passport", doc.stored_name)  # random name on disk
        r = self.c.get(f"/documents/{doc.pk}/file")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 test content")
        self.assertEqual(Client().get(f"/documents/{doc.pk}/file").status_code, 302)

    def test_bad_uploads_rejected(self):
        exe = SimpleUploadedFile("virus.exe", b"MZ....", content_type="application/octet-stream")
        self.act("document.upload", {"type": "Other", "customerId": self.cust.pk}, file=exe, status=400)
        fake = SimpleUploadedFile("fake.pdf", b"not a pdf", content_type="application/pdf")
        self.act("document.upload", {"type": "Other", "customerId": self.cust.pk}, file=fake, status=400)
        self.assertEqual(Document.objects.count(), 0)

    def test_backup_validate_and_reject_tampered(self):
        import zipfile
        from core.backup import BackupError, validate_backup
        # Tests use an in-memory DB; back up the real on-disk test DB location instead is not possible,
        # so exercise validation with a crafted archive.
        bad = Path(settings.BACKUP_ROOT) / "SafarPro-backup-bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("manifest.json", "{}")
            z.writestr("safarpro.sqlite3", b"garbage")
        with self.assertRaises(BackupError):
            validate_backup(bad)
        evil = Path(settings.BACKUP_ROOT) / "SafarPro-backup-evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("manifest.json", "{}")
            z.writestr("safarpro.sqlite3", b"x")
            z.writestr("documents/../../evil.txt", b"x")
        with self.assertRaises(BackupError):
            validate_backup(evil)


class DemoModeTests(TransactionTestCase):
    """Public online demo (SAFARPRO_DEMO=1): one-click roles, safety blocks, auto-reset, and that it is OFF by default."""

    def setUp(self):
        from web import demo
        self.demo = demo
        self.tmp = Path(tempfile.mkdtemp())
        self.ov = override_settings(DEMO_MODE=True, DATA_ROOT=self.tmp, DOCUMENTS_ROOT=self.tmp / "documents", BACKUP_ROOT=self.tmp / "backups")
        self.ov.enable()
        demo._last_check = 0.0

    def tearDown(self):
        self.ov.disable()
        self.demo._last_check = 0.0
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sign_in(self, username="demo-owner"):
        c = Client()
        c.get("/login/")  # first request builds the demo data
        r = c.post("/demo/login/", {"username": username})
        self.assertEqual(r.status_code, 302)
        return c

    def act(self, c, name, data):
        return c.post(f"/api/action/{name}", json.dumps(data), content_type="application/json")

    def test_first_request_builds_demo_with_role_accounts(self):
        r = Client().get("/login/")
        self.assertContains(r, "Try the live demo")
        self.assertTrue(Customer.objects.exists())
        for username, role, *_ in self.demo.DEMO_ACCOUNTS:
            emp = Employee.objects.get(user__username=username)
            self.assertEqual(emp.role, role)
            self.assertFalse(emp.user.has_usable_password())  # nobody can sign in with or change a password

    def test_one_click_sign_in_and_state_marks_demo(self):
        c = self.sign_in("demo-accountant")
        st = c.get("/api/state").json()["state"]
        self.assertEqual(st["me"]["role"], "Accountant")
        self.assertIsNotNone(st["app"]["demo"])

    def test_role_limits_still_enforced(self):
        c = self.sign_in("demo-reception")
        b = Booking.objects.exclude(status="Draft").first()
        r = self.act(c, "payment.create", {"bookingId": str(b.pk), "date": TODAY.isoformat(), "method": "Cash", "amount": 10})
        self.assertEqual(r.status_code, 403)

    def test_unknown_username_cannot_use_one_click_sign_in(self):
        Client().get("/login/")
        c = Client()
        c.post("/demo/login/", {"username": "admin"})
        self.assertEqual(c.get("/api/state").status_code, 401)

    def test_risky_actions_blocked_and_paths_hidden(self):
        c = self.sign_in()
        self.assertEqual(self.act(c, "me.password", {"current": "x", "password": "N3w!Passw0rd", "password2": "N3w!Passw0rd"}).status_code, 403)
        self.assertEqual(self.act(c, "backup.create", {}).status_code, 403)
        other = Employee.objects.get(user__username="demo-reception")
        self.assertEqual(self.act(c, "employee.status", {"id": str(other.pk), "reason": "x"}).status_code, 403)
        self.assertEqual(Employee.objects.get(pk=other.pk).status, "Active")
        st = c.get("/api/state").json()["state"]
        self.assertNotIn(str(self.tmp), json.dumps(st["system"]))

    def test_stale_demo_data_is_rebuilt(self):
        c = self.sign_in()
        r = self.act(c, "customer.save", {"name": "Visitor Test", "phone": "0300-1112233", "type": "Individual", "country": "Pakistan", "city": "Lahore"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Customer.objects.filter(name="Visitor Test").exists())
        (self.tmp / "demo_built_at.txt").write_text("2020-01-01T00:00:00")
        self.demo._last_check = 0.0
        Client().get("/login/")
        self.assertFalse(Customer.objects.filter(name="Visitor Test").exists())
        self.assertTrue(Customer.objects.exists())

    def test_demo_code_refuses_to_run_on_a_real_installation(self):
        with override_settings(DEMO_MODE=False):
            with self.assertRaises(RuntimeError):
                self.demo.build_demo()
            initialize(org_name="Real", city="Lahore", branch_name="Main", branch_code="LHR", admin_name="Owner", username="owner", password=PW)
            c = Client()
            self.assertEqual(c.post("/demo/login/", {"username": "demo-owner"}).status_code, 302)
            self.assertEqual(c.get("/api/state").status_code, 401)
            self.assertContains(c.get("/login/"), "Username")
            self.assertFalse((self.tmp / "demo_built_at.txt").exists())
