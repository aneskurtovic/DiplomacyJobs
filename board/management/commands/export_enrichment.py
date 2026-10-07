import json
from django.core.management.base import BaseCommand
from django.db.models import Q
from board.models import Job


class Command(BaseCommand):
    help = "Export jobs for optional manual local AI enrichment as JSON Lines"

    def add_arguments(self, parser):
        parser.add_argument("--status", choices=["review", "published"], default="review")
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--missing-requirements", action="store_true", help="only jobs without an education level, years of experience or field of study")

    def handle(self, *args, **options):
        jobs = Job.objects.filter(status=options["status"]).select_related("source__organization").order_by("-first_seen_at")
        if options["missing_requirements"]:
            jobs = jobs.filter(Q(education_level="") | Q(experience_years__isnull=True) | Q(fields_of_study=[]))
        for job in jobs[:max(0, min(options["limit"], 500))]:
            current = {"title": job.title, "city": job.city, "deadline": job.deadline.isoformat() if job.deadline else None, "application_url": job.application_url,
                       "education_level": job.education_level, "experience_years": job.experience_years, "fields_of_study": job.fields_of_study}
            self.stdout.write(json.dumps({"id": job.pk, "content_hash": job.content_hash, "employer": job.source.organization.name, "source_url": job.canonical_url, "current": current, "source_text": job.raw_text}, ensure_ascii=False))
