"""
Apply pending migrations safely. If the database already has data and there are pending
migrations (e.g. after an update), a backup is taken FIRST. Never drops or recreates data.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from core.backup import BackupError, create_backup


class Command(BaseCommand):
    help = "Back up (if needed) and apply pending database migrations."

    def handle(self, *args, **o):
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if not plan:
            self.stdout.write("Database is up to date.")
            return
        has_data = "core_organization" in connection.introspection.table_names()
        if has_data:
            try:
                path, _ = create_backup(label="before-update")
                self.stdout.write(f"Pre-update backup saved: {path}")
            except BackupError as e:
                raise CommandError(f"Could not back up before updating the database, so nothing was changed: {e}")
        self.stdout.write(f"Applying {len(plan)} database update(s)…")
        call_command("migrate", interactive=False, verbosity=1)
        self.stdout.write(self.style.SUCCESS("Database ready."))
