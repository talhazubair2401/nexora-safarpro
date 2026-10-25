from django.core.management.base import BaseCommand, CommandError

from accounts.models import Employee
from operations.models import Booking


class Command(BaseCommand):
    help = "Add fictional sample records for evaluation (only when there are no bookings yet)."

    def handle(self, *args, **o):
        if Booking.objects.exists():
            raise CommandError("This database already has bookings. Sample data is only added to an empty installation.")
        admin = Employee.objects.filter(role__in=["Administrator", "Owner"], user__isnull=False).first()
        if not admin:
            raise CommandError("Create the administrator first (run SafarPro and complete the setup screen).")
        from web.sample import load_sample_data
        load_sample_data(admin.user)
        self.stdout.write(self.style.SUCCESS("Sample data added."))
