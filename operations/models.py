from django.db import models
from django.utils import timezone
from django.db.models import Q

MONEY = dict(max_digits=14, decimal_places=2)
SERVICES = ["Air Ticket", "Visa", "Umrah", "Tour", "Hotel", "Transport", "Other"]
BOOKING_STATUSES = ["Draft", "Pending", "Confirmed", "Completed", "Cancelled", "Refunded"]


class Supplier(models.Model):
    CATEGORIES = ["Airline / Consolidator", "Hotel", "Transport Provider", "Visa Service Provider",
                  "Umrah Package Supplier", "Tour Operator", "Other Service Provider"]
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=40)
    terms_days = models.PositiveIntegerField(default=15)
    contact = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.CharField(max_length=120, blank=True)
    ntn = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, default="Active")

    class Meta:
        ordering = ["name"]


class Agent(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    city = models.CharField(max_length=80)
    contact = models.CharField(max_length=40, blank=True)
    credit_limit = models.DecimalField(**MONEY)
    opening_balance = models.DecimalField(**MONEY, default=0)
    wallet = models.DecimalField(**MONEY, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, default="Pending approval")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT)
    joined = models.DateField(default=timezone.localdate)


class UmrahPackage(models.Model):
    name = models.CharField(max_length=150)
    days = models.PositiveIntegerField()
    makkah = models.CharField(max_length=150)
    madinah = models.CharField(max_length=150)
    transport = models.CharField(max_length=150, blank=True)
    room = models.CharField(max_length=60, blank=True)
    flight = models.CharField(max_length=150, blank=True)
    cost = models.DecimalField(**MONEY)
    sell = models.DecimalField(**MONEY)
    capacity = models.PositiveIntegerField(default=40)
    status = models.CharField(max_length=20, default="Active")
    inclusions = models.JSONField(default=list)
    exclusions = models.JSONField(default=list)


class UmrahGroup(models.Model):
    ref = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    package = models.ForeignKey(UmrahPackage, on_delete=models.PROTECT)
    departure = models.DateField()
    return_date = models.DateField()
    flight = models.CharField(max_length=150, default="To be confirmed")
    return_flight = models.CharField(max_length=150, default="To be confirmed")
    leader = models.CharField(max_length=120, default="To be assigned")
    status = models.CharField(max_length=40, default="Registration open")


class Tour(models.Model):
    name = models.CharField(max_length=150)
    dest = models.CharField(max_length=120)
    region = models.CharField(max_length=20, default="Domestic")
    days = models.PositiveIntegerField()
    price = models.DecimalField(**MONEY)
    cost = models.DecimalField(**MONEY)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.PROTECT)
    color = models.CharField(max_length=10, default="#1F5F57")
    transport = models.CharField(max_length=150, blank=True)
    hotel = models.CharField(max_length=150, blank=True)
    itinerary = models.JSONField(default=list)
    inclusions = models.JSONField(default=list)
    exclusions = models.JSONField(default=list)
    policy = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="Active")


class Departure(models.Model):
    tour = models.ForeignKey(Tour, on_delete=models.PROTECT, related_name="departures")
    date = models.DateField()
    capacity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default="Scheduled")

    class Meta:
        unique_together = [("tour", "date")]
        ordering = ["date"]


class Booking(models.Model):
    ref = models.CharField(max_length=24, unique=True)
    customer = models.ForeignKey("crm.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    service = models.CharField(max_length=20)
    destination = models.CharField(max_length=200)
    travel_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    pax = models.PositiveIntegerField(default=1)
    passengers = models.JSONField(default=list)
    price = models.DecimalField(**MONEY)
    cost = models.DecimalField(**MONEY, default=0)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    status = models.CharField(max_length=20, default="Pending", db_index=True)
    employee = models.ForeignKey("accounts.Employee", on_delete=models.PROTECT)
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT)
    created = models.DateField()
    posted_on = models.DateField(null=True, blank=True, db_index=True)  # date invoiced (revenue recognised)
    notes = models.TextField(blank=True)
    departure = models.ForeignKey(Departure, null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    group = models.ForeignKey(UmrahGroup, null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    airline = models.CharField(max_length=60, blank=True)
    enquiry = models.ForeignKey("crm.Enquiry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cancelled_on = models.DateField(null=True, blank=True)
    cancel_fee = models.DecimalField(**MONEY, null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    supplier_credit = models.DecimalField(**MONEY, default=0)  # credit note received from supplier on cancellation
    timeline = models.JSONField(default=list)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0) & Q(cost__gte=0), name="booking_amounts_non_negative"),
            models.CheckConstraint(condition=Q(customer__isnull=False) | Q(agent__isnull=False), name="booking_has_party"),
        ]


class Ticket(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="tickets")
    passenger = models.CharField(max_length=150)
    airline = models.CharField(max_length=60)
    number = models.CharField(max_length=20, unique=True)
    pnr = models.CharField(max_length=10)
    origin = models.CharField(max_length=3)
    dest = models.CharField(max_length=3)
    dep = models.DateField()
    ret = models.DateField(null=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    cost = models.DecimalField(**MONEY)
    sell = models.DecimalField(**MONEY)
    fee = models.DecimalField(**MONEY, default=0)
    commission = models.DecimalField(**MONEY, default=0)
    status = models.CharField(max_length=20, default="Issued")
    employee = models.ForeignKey("accounts.Employee", on_delete=models.PROTECT)
    created = models.DateField(default=timezone.localdate)


class VisaApplication(models.Model):
    STAGES = ["New Enquiry", "Documents Pending", "Documents Verified", "Ready to Submit", "Submitted", "Processing",
              "Additional Information Required", "Approved", "Rejected", "Passport Returned", "Closed"]
    ref = models.CharField(max_length=20, unique=True)
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="visa")
    country = models.CharField(max_length=80)
    type = models.CharField(max_length=80)
    status = models.CharField(max_length=40)
    submitted = models.DateField(null=True, blank=True)
    expected = models.DateField(null=True, blank=True)
    embassy_fee = models.DecimalField(**MONEY)
    service_fee = models.DecimalField(**MONEY)
    officer = models.ForeignKey("accounts.Employee", on_delete=models.PROTECT)
    created = models.DateField(default=timezone.localdate)
    docs = models.JSONField(default=list)
    timeline = models.JSONField(default=list)
    reminders = models.JSONField(default=list)
    notes = models.TextField(blank=True)


class Pilgrim(models.Model):
    group = models.ForeignKey(UmrahGroup, on_delete=models.PROTECT, related_name="pilgrims")
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.PROTECT, related_name="pilgrims")
    name = models.CharField(max_length=150)
    gender = models.CharField(max_length=2, default="—")
    passport_status = models.CharField(max_length=20, default="Missing")
    passport_masked = models.CharField(max_length=20, blank=True)
    visa_status = models.CharField(max_length=30, default="Pending documents")
    room = models.CharField(max_length=80, blank=True)
    payment_status = models.CharField(max_length=20, default="Pending")
    emergency = models.CharField(max_length=120, blank=True)
    special = models.CharField(max_length=200, blank=True)


class HotelReservation(models.Model):
    hotel = models.CharField(max_length=150)
    city = models.CharField(max_length=80)
    country = models.CharField(max_length=80)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    room = models.CharField(max_length=60)
    check_in = models.DateField()
    check_out = models.DateField()
    rooms = models.PositiveIntegerField(default=1)
    conf = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=30, default="Pending confirmation")
    group = models.ForeignKey(UmrahGroup, null=True, blank=True, on_delete=models.SET_NULL)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)
    contact = models.CharField(max_length=120, blank=True)


class TransportArrangement(models.Model):
    type = models.CharField(max_length=80)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    origin = models.CharField(max_length=150)
    destination = models.CharField(max_length=150)
    at = models.DateTimeField()
    pax = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=30, default="Pending confirmation")
    group = models.ForeignKey(UmrahGroup, null=True, blank=True, on_delete=models.SET_NULL)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)
    conf = models.CharField(max_length=40, blank=True)


class AgentRequest(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="requests")
    service = models.CharField(max_length=20)
    desc = models.CharField(max_length=250)
    pax = models.PositiveIntegerField(default=1)
    travel_date = models.DateField()
    amount = models.DecimalField(**MONEY)
    cost = models.DecimalField(**MONEY)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.PROTECT)
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, default="Pending")
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=250, blank=True)
