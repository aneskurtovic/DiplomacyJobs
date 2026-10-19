import logging
import signal
import sys
import time
from datetime import UTC, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from board.management.commands.scrape_jobs import INTERRUPTED, lock_path
from board.models import ScrapeRun

logger = logging.getLogger(__name__)


def seconds_until_next_run(now):
    """Use real hourly boundaries, including both copies of a repeated DST hour."""
    utc_now = now.astimezone(UTC)
    target = utc_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return (target - utc_now).total_seconds()


class Command(BaseCommand):
    help = "Run due sources hourly in the dedicated scheduler container"

    def run_once(self, **options):
        try:
            # A sleeping scheduler may outlive a database restart.
            close_old_connections()
            call_command("scrape_jobs", **options)
        except Exception:
            logger.exception("Scheduled scrape failed (source=%s)", options.get("source", "all"))

    def handle(self, *args, **options):
        # docker stop sends SIGTERM; exiting through SystemExit lets scrape_jobs remove its lock.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        # This is the only scraper in its container, so a lock present at startup was left by a killed run.
        lock_path().unlink(missing_ok=True)
        # Likewise an unfinished run was killed with it; closing it lets the overlap guard in ingest_source pass.
        ScrapeRun.objects.filter(finished_at__isnull=True).update(finished_at=timezone.now(), error=INTERRUPTED)
        # The scheduled command checks each source's latest non-interrupted attempt.
        # A redeploy therefore catches missed sources without refetching recent ones.
        self.run_once(scheduled=True)
        while True:
            time.sleep(seconds_until_next_run(timezone.localtime()))
            self.run_once(scheduled=True)
