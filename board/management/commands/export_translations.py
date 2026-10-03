import json

from django.core.management.base import BaseCommand

from board import translation
from board.models import Job
from board.views import visible_jobs


class Command(BaseCommand):
    help = "Export current public jobs that need Bosnian and English versions as JSON Lines, for the local translate-jobs skill."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10, help="At most this many jobs (default 10).")
        parser.add_argument("--job", type=int, action="append", help="Export this published job even if it already has a translation (repeatable).")

    def handle(self, *args, limit=10, job=None, **options):
        if job:
            jobs = list(Job.objects.filter(pk__in=job, status="published").select_related("source__organization"))
        else:
            jobs = translation.pending(visible_jobs().select_related("source__organization").order_by("-first_seen_at", "-pk"))[:max(0, min(limit, 200))]
        for item in jobs:
            self.stdout.write(json.dumps({"id": item.pk, "content_hash": item.content_hash, "title": item.title, "employer": item.employer_name, "detected_language": (item.requirements or {}).get("language", ""), "source_url": item.canonical_url, "source_text": item.raw_text}, ensure_ascii=False))
