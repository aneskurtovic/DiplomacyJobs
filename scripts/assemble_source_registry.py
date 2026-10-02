"""Merge verified local MFA mission entries with researched recruitment endpoints."""
import json
from pathlib import Path

inventory_path = Path("data/mfa_inventory.json")
registry_path = Path("data/source_registry.json")
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
curated = json.loads(registry_path.read_text(encoding="utf-8"))
curated_by_title = {
    "JAPAN": "Ambasada Japana u Bosni i Hercegovini",
    "UK": "Britanska ambasada u Sarajevu",
    "United States of America": "Ambasada Sjedinjenih Američkih Država u BiH",
}
curated_by_name = {row["name"]: row for row in curated}
skip = {"FRANCE - Office of the Defence Attaché", "FRANCE - Culture Department", "FRANCE - Economic Department", "UK - Office in Banja Luka"}
result = []
for item in inventory:
    title = item["directory_title"]
    if not item["city"] or title in skip:
        continue
    name = curated_by_title.get(title, item["name"].lstrip("\ufeff").strip())
    kind = item["kind"] if item["kind"] != "other" else "embassy"
    city = "Sarajevo" if title == "SLOVENIA" else item["city"]
    website = item["website"]
    if website and not website.startswith(("http://", "https://")):
        website = ""
    existing = curated_by_name.pop(name, {})
    result.append({
        "name": name,
        "kind": kind,
        "country": title.split(" - ", 1)[0].split(" – ", 1)[0].strip(),
        "city": city,
        "website": existing.get("website") or website,
        "evidence_url": item["detail_url"],
        "verified_at": "2026-10-02",
        "notes": (existing.get("notes", "") + " Adresa iz MFA direktorija. MFA web-adresa, ako postoji, zahtijeva zasebnu provjeru aktuelnosti.").strip(),
        "sources": existing.get("sources", []),
    })
result.extend(curated_by_name.values())
result.sort(key=lambda row: row["name"].casefold())
registry_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for item in inventory:
    if item["city"]:
        item["verification"] = "resident"
    elif item.get("address"):
        item["verification"] = "nonresident_or_unconfirmed"
inventory_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Registry now has {len(result)} organizations, including {len(result)-len(curated_by_name)} local MFA missions")
