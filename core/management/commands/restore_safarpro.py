from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from core.backup import BackupError, restore_backup, validate_backup


class Command(BaseCommand):
    help = "Validate and restore a SafarPro backup. A safety backup of the current data is taken first."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--validate-only", action="store_true")
        parser.add_argument("--yes", action="store_true", help="Skip the typed confirmation (used by restore_safarpro.bat after it has asked)")

    def handle(self, *args, **o):
        try:
            m = validate_backup(o["file"])
        except BackupError as e:
            raise CommandError(f"Backup rejected: {e}")
        c = m.get("counts", {})
        self.stdout.write(f"Backup is valid. Created {m.get('created')} (app version {m.get('version')}).")
        self.stdout.write(f"  Contains {c.get('customers')} customers, {c.get('bookings')} bookings, {c.get('payments')} payments, {m.get('documents')} documents.")
        if o["validate_only"]:
            return
        if not o["yes"]:
            ans = input("This REPLACES your current SafarPro data (a safety backup is taken first). Type RESTORE to continue: ")
            if ans.strip() != "RESTORE":
                raise CommandError("Restore cancelled. Nothing was changed.")
        try:
            m, safety = restore_backup(o["file"])
        except BackupError as e:
            raise CommandError(f"Restore failed: {e}")
        if safety:
            self.stdout.write(f"Safety backup of your previous data: {safety}")
        call_command("migrate", interactive=False, verbosity=0)
        self.stdout.write(self.style.SUCCESS("Restore completed. Start SafarPro with run_safarpro.bat."))
