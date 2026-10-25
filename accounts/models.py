from django.conf import settings
from django.db import models
from django.utils import timezone

ROLES = [
    "Owner", "Administrator", "Branch Manager", "Accountant", "Ticketing Officer", "Visa Officer",
    "Tour Operations Officer", "Receptionist", "Read-Only Auditor",
]


class Employee(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee")
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=40, choices=[(r, r) for r in ROLES], default="Receptionist")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="employees")
    email = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, default="Active")
    joined = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name
