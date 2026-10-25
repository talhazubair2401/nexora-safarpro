from django.core.management.base import BaseCommand, CommandError

from core.backup import BackupError, create_backup, list_backups


class Command(BaseCommand):
    help = "Create a validated backup (database + documents) in the SafarPro backups folder."

    def add_arguments(self, parser):
        parser.add_argument("--label", default="manual")
        parser.add_argument("--list", action="store_true", help="List existing backups")

    def handle(self, *args, **o):
        if o["list"]:
            for b in list_backups():
                self.stdout.write(f"{b['at']}  {b['size'] / 1024:>9.0f} KB  {b['name']}")
            return
        try:
            path, m = create_backup(label=o["label"])
        except BackupError as e:
            raise CommandError(str(e))
        c = m["counts"]
        self.stdout.write(self.style.SUCCESS(f"Backup created and verified:\n  {path}"))
        self.stdout.write(f"  {c.get('customers')} customers, {c.get('bookings')} bookings, {c.get('payments')} payments, {m['documents']} documents")
