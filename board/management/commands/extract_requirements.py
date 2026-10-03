from django.core.management.base import BaseCommand

from board import requirements
from board.models import Job


class Command(BaseCommand):
    help = "Re-read education, experience and other requirements from the stored text of every job. Admin corrections are kept."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change without saving.")

    def handle(self, *args, dry_run=False, **options):
        updated = 0
        for job in Job.objects.order_by("pk"):
            changed = requirements.apply(job)
            if not changed:
                continue
            updated += 1
            summary = ", ".join(requirements.tags(job)) or "nema izdvojenih uslova"
            self.stdout.write(f"{job.pk} {job.title[:60]}: {summary}")
            if not dry_run:
                job.save(update_fields=changed)
        self.stdout.write(self.style.SUCCESS(f"{updated} oglasa {'bi se promijenilo' if dry_run else 'ažurirano'}."))
