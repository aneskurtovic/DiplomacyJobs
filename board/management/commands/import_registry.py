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
            # previous_name renames an organization instead of leaving the old one behind.
            if item.get("previous_name") and not Organization.objects.filter(name=item["name"]).exists():
                Organization.objects.filter(name=item["previous_name"]).update(name=item["name"])
            organization, _ = Organization.objects.update_or_create(name=item["name"], defaults={key: (item.get(key) or None) if key == "verified_at" else (item.get(key) or "") for key in ("kind", "country", "city", "website", "evidence_url", "verified_at", "notes")})
            for entry in item.get("sources", []):
                # Registry updates metadata and parser settings but never silently enables a source or swaps a running parser. A URL is one source even if the registry moves it to another organization.
                source = Source.objects.filter(url=entry["url"]).first()
                if source is None:
                    Source.objects.create(organization=organization, url=entry["url"], adapter=entry.get("adapter", "none"), status=entry.get("status", "discovered"), enabled=entry.get("enabled", False), adapter_config=entry.get("adapter_config", {}), notes=entry.get("notes", ""))
                else:
                    source.organization = organization
                    source.notes = entry.get("notes", source.notes)
                    source.adapter_config = entry.get("adapter_config", source.adapter_config)
                    if not source.enabled:
                        source.adapter = entry.get("adapter", source.adapter)
                    source.save(update_fields=["organization", "notes", "adapter_config", "adapter"])
        self.stdout.write(self.style.SUCCESS(f"Imported {len(data)} organizations"))
