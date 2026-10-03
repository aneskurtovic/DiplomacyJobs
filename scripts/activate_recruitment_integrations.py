"""Apply and live-check only the seven disabled October-audit integrations.

Run after taking a database backup. A failed check leaves the source disabled.
This does not activate unrelated discovery sources or run the global expiry pass.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.core.management import call_command
from django.utils import timezone
from board.ingest import ingest_source
from board.models import Job, Source

path = Path("data/source_registry.json")
registry = json.loads(path.read_text(encoding="utf-8"))
targets = [item for item in registry if item.get("recruitment_status") == "integration"]
if len(targets) != 7 or {item["sources"][0]["adapter"] for item in targets} != {"rmk", "turkey", "brazil", "spain", "slovenia", "canadales"}:
    raise ValueError("Expected exactly the seven reviewed audit integrations")
call_command("migrate", interactive=False)
call_command("import_registry")
results = []
before = Job.objects.count()
for item in targets:
    entry = item["sources"][0]
    source = Source.objects.get(url=entry["url"])
    source.enabled = True
    source.save(update_fields=["enabled"])
    run = ingest_source(source.pk)
    success = bool(run and run.success)
    note = {
        "rmk": "MoFA SuccessFactors: potpuna paginacija i filtriranje mjesta rada u BiH; dva trenutna oglasa su u UAE.",
        "turkey": "Turska lokalna lista: javni odabir jezika, lokalni izdavač, datumi i pojmovi zapošljavanja; bez novih oglasa za 2026.",
        "brazil": "Djelimično praćenje: folder, BHS stranica i PDF; trenutni proces je zatvoren. PDF je skeniran; otvoren dokument bez čitljivog teksta izaziva grešku i zahtijeva OCR/provjeru.",
        "spain": "Španska lista i PDF poziva: datumi, kategorije, izmjene i završeni procesi; Auxiliar 2026 je završen i nije objavljen kao otvoren posao.",
        "slovenia": "MZEZ: aktivni konkursi i paginacija, zaseban dokaz lokalnog poslodavca/mjesta rada; isključena posmatranja izbora i druge misije.",
        "canadales": "Djelimično praćenje globalnog LES portala: javni podaci i registri misija, zaseban dokaz mjesta rada i poslodavca. Sarajevo počasni konzulat nije naveden u portalu; njegovi zasebni oglasi nisu potpuno pokriveni. Nema potvrđenog lokalnog oglasa.",
    }[entry["adapter"]]
    if not success:
        source.enabled = False
        source.save(update_fields=["enabled"])
        note = "Provjera integracije nije uspjela: " + (run.error if run else "prethodni scrape još traje")
    source.notes = f"2026-10-03: {note}"
    source.save(update_fields=["notes"])
    entry.update(enabled=success, status="verified" if success else "unsupported", notes=source.notes)
    item.update(recruitment_checked_at="2026-10-03", recruitment_notes=note)
    source.organization.recruitment_notes = note
    source.organization.recruitment_checked_at = timezone.localdate()
    source.organization.save(update_fields=["recruitment_notes", "recruitment_checked_at"])
    result = {"source_id": source.pk, "organization": item["name"], "url": source.url, "adapter": source.adapter, "success": success, "candidates": run.candidates if run else None, "error": run.error if run else "No run", "checked_at": timezone.now().isoformat(), "partial": bool(source.adapter_config.get("partial_listing"))}
    results.append(result)
    print(json.dumps(result, ensure_ascii=True), flush=True)
path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
report = {"checked_at": timezone.now().isoformat(), "jobs_before": before, "jobs_after": Job.objects.count(), "sources": results}
Path("data/recruitment_integration_2026-10-03.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if not all(result["success"] for result in results):
    raise SystemExit("Some integrations remain disabled; see report")
