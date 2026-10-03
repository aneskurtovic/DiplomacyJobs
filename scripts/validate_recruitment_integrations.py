"""Live, read-only listing and candidate validation for the seven audit leads."""
import json
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from bs4 import BeautifulSoup
from board.ingest import CARD_EVIDENCE, FEED_ADAPTERS, discover_links, fetch, make_candidate, open_client
from board.models import Organization, Source

results = []
parser = argparse.ArgumentParser()
parser.add_argument("--adapter")
options = parser.parse_args()
items = json.loads(Path("data/source_registry.json").read_text(encoding="utf-8"))
for item in items:
    if item.get("recruitment_status") != "integration":
        continue
    entry = item["sources"][0]
    if options.adapter and entry["adapter"] != options.adapter:
        continue
    source = Source(organization=Organization(name=item["name"], city=item["city"]), **{key: entry[key] for key in ("url", "adapter", "adapter_config")})
    result = {"organization": item["name"], "url": source.url, "adapter": source.adapter}
    try:
        with open_client(source) as client:
            soup = BeautifulSoup("", "html.parser") if source.adapter in FEED_ADAPTERS else fetch(client, source.url)[1]
            evidence = {}
            links = discover_links(client, source, soup, evidence)
            result["leads"] = len(links)
            candidates = []
            for url, title in links:
                body, detail = (evidence[url], None) if source.adapter in CARD_EVIDENCE else fetch(client, url)
                candidate = make_candidate(source, url, title, body, detail, "" if source.adapter in CARD_EVIDENCE else evidence.get(url, ""))
                candidates.append({"url": url, "title": candidate.title, "published": str(candidate.source_published_at), "deadline": str(candidate.deadline), "eligible": candidate.eligible, "withdrawn": candidate.withdrawn, "reason": candidate.reason})
            result.update(success=True, candidates=candidates)
    except Exception as exc:
        result.update(success=False, error=f"{type(exc).__name__}: {exc}")
    print(json.dumps(result, ensure_ascii=True), flush=True)
    results.append(result)
filename = "validation" + (f"-{options.adapter}" if options.adapter else "") + ".json"
output = Path("data/raw/integration_2026-10-03", filename)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
if not results or not all(result["success"] for result in results):
    raise SystemExit("No matching integrations or failed source checks; see report")
