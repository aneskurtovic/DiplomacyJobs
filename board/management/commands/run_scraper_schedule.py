import signal
import sys
import time
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from board.management.commands.scrape_jobs import lock_path
from board.models import ScrapeRun

RUN_AT_HOUR = 6


def seconds_until_next_run(now):
    """Runs start at a fixed local hour, so they do not drift later by each run's duration."""
    target = now.replace(hour=RUN_AT_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


class Command(BaseCommand):
    help = "Run daily scraping in the dedicated scheduler container"

    def run_once(self):
        try:
            call_command("scrape_jobs")
        except Exception as exc:
            self.stderr.write(str(exc))

    def handle(self, *args, **options):
        # docker stop sends SIGTERM; exiting through SystemExit lets scrape_jobs remove its lock.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        # This is the only scraper in its container, so a lock present at startup was left by a killed run.
        lock_path().unlink(missing_ok=True)
        # A restart or redeploy does not add an extra run when today's has happened.
        if not ScrapeRun.objects.filter(started_at__gte=timezone.now() - timedelta(hours=20)).exists():
            self.run_once()
        while True:
            time.sleep(seconds_until_next_run(timezone.localtime()))
            self.run_once()
