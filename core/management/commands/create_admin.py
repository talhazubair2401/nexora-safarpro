import getpass

from django.core.management.base import BaseCommand, CommandError

from core.setup import initialize, needs_setup
from core.validation import ActionError


class Command(BaseCommand):
    help = "Create the first administrator from the command line (alternative to the first-run web page)."

    def handle(self, *args, **o):
        if not needs_setup():
            raise CommandError("An administrator already exists. Add more users from Employees & Roles in the app.")
        ask = lambda q, d="": input(f"{q}{f' [{d}]' if d else ''}: ").strip() or d
        org = ask("Agency name")
        city = ask("City", "Lahore")
        bname = ask("Main branch name", f"{city} Main Branch")
        bcode = ask("Branch code (2-6 letters)", city[:3].upper())
        name = ask("Administrator full name")
        user = ask("Username")
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repeat password: "):
            raise CommandError("Passwords do not match.")
        try:
            initialize(org_name=org, city=city, branch_name=bname, branch_code=bcode, admin_name=name, username=user, password=pw)
        except ActionError as e:
            raise CommandError("; ".join(f"{k}: {v}" for k, v in e.errors.items()) or e.message)
        self.stdout.write(self.style.SUCCESS(f"Administrator '{user}' created. Start SafarPro and sign in."))
