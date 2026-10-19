import logging
import os
import time
from datetime import timedelta
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from board.dedup import reconcile_aggregator_duplicates
from board.ingest import archive_source, expire_jobs, ingest_source
from board.models import ScrapeRun, Source

STALE_LOCK_SECONDS = 6 * 60 * 60
INTERRUPTED = "Interrupted: the scheduler restarted during this run"
logger = logging.getLogger(__name__)


def lock_path():
    return Path("/tmp/diplomacyjobs-scrape.lock") if os.name != "nt" else Path(os.environ.get("TEMP", ".")) / "diplomacyjobs-scrape.lock"


def due_sources(sources, now):
    """Respect each source's minimum interval, including failed attempts."""
    previous = (ScrapeRun.objects.filter(source_id=OuterRef("pk"))
                .exclude(error=INTERRUPTED).order_by("-started_at").values("started_at")[:1])
    for source in sources.annotate(previous_attempt=Subquery(previous)):
        # Existing production rows may not have the registry's new interval yet.
        default_hours = 24 if source.adapter == "undpnotices" else 1
        hours = max(1, int((source.adapter_config or {}).get("min_scrape_interval_hours", default_hours)))
        if source.previous_attempt is None or source.previous_attempt <= now - timedelta(hours=hours):
            yield source


class Command(BaseCommand):
    help = "Fetch enabled official recruitment sources once"

    def add_arguments(self, parser):
        parser.add_argument("--source", type=int)
        parser.add_argument("--scheduled", action="store_true", help="Skip sources checked within their minimum interval")
        # A one-off backfill, not part of the schedule: ended adverts of a past or the current year, stored as closed.
        parser.add_argument("--history", type=int, metavar="YEAR", help="Store this year's ended adverts from sources with history settings")

    def handle(self, *args, **options):
        lock = lock_path()
        # A run takes minutes. An older lock was left by a killed process; /tmp survives container restarts.
        if lock.exists() and time.time() - lock.stat().st_mtime > STALE_LOCK_SECONDS:
            self.stderr.write(f"Removing stale scrape lock from {time.ctime(lock.stat().st_mtime)}")
            lock.unlink(missing_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise CommandError("Scrape already running; inspect the lock if a process crashed") from exc
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            sources = Source.objects.filter(enabled=True).exclude(adapter="none")
            if options["source"]:
                sources = sources.filter(pk=options["source"])
                if not sources.exists():
                    raise CommandError(f"No enabled source with id {options['source']}")
            if options["history"]:
                self.archive(sources, options["history"])
                return
            if options["scheduled"]:
                sources = due_sources(sources, timezone.now())
            try:
                for source in sources:
                    # One source's unexpected error must not skip the rest or the expiry pass.
                    try:
                        result = ingest_source(source.pk)
                    except Exception as exc:
                        logger.exception("Source %s: unexpected scrape error", source.pk)
                        self.stderr.write(f"{source.pk}: unexpected error: {exc}")
                        continue
                    if result is None:
                        self.stdout.write(f"{source.pk}: skipped, another run is in progress")
                    else:
                        self.stdout.write(f"{source.pk}: {'ok' if result.success else result.error}")
            finally:
                expire_jobs()
                closed = reconcile_aggregator_duplicates()
                if closed:
                    self.stdout.write(f"{closed} syndicated copies closed as duplicates")
        finally:
            lock.unlink(missing_ok=True)

    def archive(self, sources, year):
        sources = [source for source in sources if "history" in (source.adapter_config or {})]
        if not sources:
            raise CommandError("No enabled source with history settings")
        for source in sources:
            try:
                jobs = archive_source(source.pk, year)
            except Exception as exc:
                logger.exception("Source %s: archive backfill error", source.pk)
                self.stderr.write(f"{source.pk}: {exc}")
                continue
            public = sum(1 for job in jobs if job.published_at)
            self.stdout.write(f"{source.pk}: {len(jobs)} archived, {public} listed on the employer page")
