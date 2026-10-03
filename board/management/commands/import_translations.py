import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from board import translation
from board.models import Job


class Command(BaseCommand):
    help = "Validate and import Bosnian and English job versions written by the local translate-jobs skill."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--translator", default="claude-code", help="Recorded with each translation, e.g. the model that wrote it.")

    def handle(self, *args, path, translator, **options):
        path = Path(path)
        if not path.is_file():
            raise CommandError(f"File missing: {path}")
        applied = rejected = 0
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                with transaction.atomic():
                    job = Job.objects.select_for_update().get(pk=item["id"], status="published")
                    translation.store(job, item, translator)
                applied += 1
            except (ValueError, KeyError, TypeError, Job.DoesNotExist) as exc:
                rejected += 1
                self.stderr.write(f"line {line_number}: rejected: {exc}")
        self.stdout.write(f"{applied} imported, {rejected} rejected")
