import json
from django.core.management.base import BaseCommand
from board.models import Job


class Command(BaseCommand):
    help = "Export jobs for optional manual local AI enrichment as JSON Lines"

    def add_arguments(self, parser):
        parser.add_argument("--status", choices=["review", "published"], default="review")
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        jobs = Job.objects.filter(status=options["status"]).select_related("source__organization").order_by("-first_seen_at")[:max(0, min(options["limit"], 500))]
        for job in jobs:
            self.stdout.write(json.dumps({"id": job.pk, "content_hash": job.content_hash, "employer": job.source.organization.name, "source_url": job.canonical_url, "current": {"title": job.title, "city": job.city, "deadline": job.deadline.isoformat() if job.deadline else None, "application_url": job.application_url}, "source_text": job.raw_text}, ensure_ascii=False))
