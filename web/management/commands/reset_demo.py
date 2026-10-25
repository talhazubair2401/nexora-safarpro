from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Online demo only (SAFARPRO_DEMO=1): rebuild the fictional demo data now."

    def handle(self, *args, **opts):
        if not settings.DEMO_MODE:
            raise CommandError("Refusing to run: this command only works when SAFARPRO_DEMO=1. It never touches a real installation.")
        from web.demo import build_demo, next_reset
        build_demo()
        self.stdout.write(self.style.SUCCESS(f"Demo data rebuilt. Next automatic reset: {next_reset():%d %b %Y %H:%M}."))
