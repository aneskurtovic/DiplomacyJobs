import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from board.models import Organization, Source


class Command(BaseCommand):
    help = "Import the reviewed organization/source inventory"

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default="data/source_registry.json")

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Registry file missing: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data:
            organization, _ = Organization.objects.update_or_create(name=item["name"], defaults={key: item.get(key) or None if key == "verified_at" else item.get(key, "") for key in ("kind", "country", "city", "website", "evidence_url", "verified_at", "notes")})
            for entry in item.get("sources", []):
                # Registry updates metadata but never silently enable new parsers.
                source, created = Source.objects.get_or_create(organization=organization, url=entry["url"], defaults={"adapter": entry.get("adapter", "none"), "status": entry.get("status", "discovered"), "adapter_config": entry.get("adapter_config", {}), "notes": entry.get("notes", "")})
                if not created:
                    source.notes = entry.get("notes", source.notes)
                    source.save(update_fields=["notes"])
        self.stdout.write(self.style.SUCCESS(f"Imported {len(data)} organizations"))
