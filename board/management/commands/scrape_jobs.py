import os
import time
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from board.ingest import expire_jobs, ingest_source
from board.models import Source

STALE_LOCK_SECONDS = 6 * 60 * 60


class Command(BaseCommand):
    help = "Fetch enabled official recruitment sources once"

    def add_arguments(self, parser):
        parser.add_argument("--source", type=int)

    def handle(self, *args, **options):
        lock = Path("/tmp/diplomacyjobs-scrape.lock") if os.name != "nt" else Path(os.environ.get("TEMP", ".")) / "diplomacyjobs-scrape.lock"
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
            for source in sources:
                result = ingest_source(source.pk)
                if result:
                    self.stdout.write(f"{source.pk}: {'ok' if result.success else result.error}")
            expire_jobs()
        finally:
            lock.unlink(missing_ok=True)
