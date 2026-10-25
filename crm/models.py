from django.db import models
from django.utils import timezone

MONEY = dict(max_digits=14, decimal_places=2)


class Customer(models.Model):
    TYPES = ["Individual", "Corporate", "Group Organizer"]
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=20, default="Individual")
    phone = models.CharField(max_length=30, db_index=True)
    phone_norm = models.CharField(max_length=20, db_index=True)
    email = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=80)
    country = models.CharField(max_length=80, default="Pakistan")
    address = models.CharField(max_length=250, blank=True)
    cnic_masked = models.CharField(max_length=20, blank=True)
    passport_masked = models.CharField(max_length=20, blank=True)
    passport_expiry = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, default="Active")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    created = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Enquiry(models.Model):
    STAGES = ["New", "Contacted", "Quotation Sent", "Follow-up Required", "Converted", "Lost"]
    ref = models.CharField(max_length=20, unique=True)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT)
    lead = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    service = models.CharField(max_length=20)
    dest = models.CharField(max_length=150)
    travel_date = models.DateField()
    value = models.DecimalField(**MONEY)
    employee = models.ForeignKey("accounts.Employee", on_delete=models.PROTECT)
    stage = models.CharField(max_length=30, default="New")
    source = models.CharField(max_length=30, default="Walk-in")
    next_follow = models.DateField(null=True, blank=True)
    created = models.DateField(default=timezone.localdate)
    booking = models.ForeignKey("operations.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="converted_from")
    lost_reason = models.CharField(max_length=250, blank=True)
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT)
    history = models.JSONField(default=list)


class Quote(models.Model):
    ref = models.CharField(max_length=20, unique=True)
    to = models.CharField(max_length=150)
    title = models.CharField(max_length=200)
    items = models.JSONField(default=list)
    total = models.DecimalField(**MONEY)
    valid_until = models.DateField()
    terms = models.CharField(max_length=300, blank=True)
    enquiry = models.ForeignKey(Enquiry, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateField(default=timezone.localdate)


class Communication(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="comms")
    at = models.DateTimeField(auto_now_add=True)
    channel = models.CharField(max_length=20)
    direction = models.CharField(max_length=20)
    text = models.TextField()
    by = models.CharField(max_length=120)


class Document(models.Model):
    TYPES = ["Passport", "CNIC", "Visa", "Ticket", "Hotel Voucher", "Invoice", "Receipt", "Travel Insurance", "Other"]
    type = models.CharField(max_length=30)
    original_name = models.CharField(max_length=200)
    stored_name = models.CharField(max_length=80, unique=True)  # random name on disk; never derived from user input
    size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=100)
    sha256 = models.CharField(max_length=64)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="documents")
    booking = models.ForeignKey("operations.Booking", null=True, blank=True, on_delete=models.PROTECT, related_name="documents")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.CharField(max_length=120)
    expiry = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, default="Pending verification")

    class Meta:
        ordering = ["-uploaded_at"]
