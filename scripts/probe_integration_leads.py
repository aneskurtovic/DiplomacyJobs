"""Read-only HTTPS evidence capture for the seven recruitment audit leads."""
import concurrent.futures
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ROOT = Path("data/raw/integration_2026-10-03")


def probe(pair):
    index, item = pair
    url = item["sources"][0]["url"]
    result = {"index": index, "organization": item["name"], "url": url,
              "checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        response = httpx.get(url, follow_redirects=True, timeout=60)
        (ROOT / f"{index}.html").write_text(response.text, encoding="utf-8")
        soup = BeautifulSoup(response.text, "html.parser")
        links = [(a.get_text(" ", strip=True)[:200], a["href"]) for a in soup.select("a[href]")]
        (ROOT / f"{index}.links.json").write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
        result.update(status=response.status_code, size=len(response.content), final_url=str(response.url), title=soup.title.get_text() if soup.title else "")
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return result


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    items = [o for o in json.loads(Path("data/source_registry.json").read_text(encoding="utf-8")) if o.get("recruitment_status") == "integration"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        results = list(executor.map(probe, enumerate(items)))
    (ROOT / "checks.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
