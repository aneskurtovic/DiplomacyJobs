import signal
import sys
import time
from datetime import UTC, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from board.management.commands.scrape_jobs import lock_path
from board.models import ScrapeRun, Source

RUN_AT_HOUR = 6


def seconds_until_next_run(now):
    """Runs start at a fixed local hour, so they do not drift later by each run's duration."""
    target = now.replace(hour=RUN_AT_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    # Aware datetimes in one zone subtract by wall clock; through UTC the DST change day is an hour shorter or longer.
    return (target.astimezone(UTC) - now.astimezone(UTC)).total_seconds()


class Command(BaseCommand):
    help = "Run daily scraping in the dedicated scheduler container"

    def run_once(self, **options):
        try:
            call_command("scrape_jobs", **options)
        except Exception as exc:
            self.stderr.write(str(exc))

    def handle(self, *args, **options):
        # docker stop sends SIGTERM; exiting through SystemExit lets scrape_jobs remove its lock.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        # This is the only scraper in its container, so a lock present at startup was left by a killed run.
        lock_path().unlink(missing_ok=True)
        # A restart or redeploy does not add an extra run when today's has happened, but finishes one it interrupted.
        recent = ScrapeRun.objects.filter(started_at__gte=timezone.now() - timedelta(hours=20)).values("source_id")
        missing = list(Source.objects.filter(enabled=True).exclude(adapter="none").exclude(pk__in=recent).values_list("pk", flat=True))
        if missing and not recent.exists():
            self.run_once()
        else:
            for pk in missing:
                self.run_once(source=pk)
        while True:
            time.sleep(seconds_until_next_run(timezone.localtime()))
            self.run_once()
