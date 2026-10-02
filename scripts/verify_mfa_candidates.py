"""Visit each official BiH MFA entry and extract its published address and website.

This produces a research artifact; it does not mark an employer or scraper operational.
"""
import json
import re
import ssl
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
candidates = json.loads(input_path.read_text(encoding="utf-8"))
results = []
headers = {"User-Agent": "DiplomacyJobs source research/0.1"}
with httpx.Client(headers=headers, follow_redirects=True, timeout=20, verify=ssl.create_default_context()) as client:
    for index, item in enumerate(candidates, 1):
        url = f"https://mvp.gov.ba/en/{item['directory_slug']}"
        result = {**item, "detail_url": url, "verification": "failed", "name": "", "address": "", "website": "", "city": "", "kind": ""}
        try:
            response = client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            headings = [x.get_text(" ", strip=True) for x in soup.find_all("h1")]
            result["name"] = headings[-1] if headings else item["directory_title"]
            for paragraph in soup.find_all("p"):
                strong = paragraph.find("strong")
                label = strong.get_text(" ", strip=True).lower().rstrip(":") if strong else ""
                if label in ("address", "adresa"):
                    result["address"] = paragraph.get_text(" ", strip=True).split(":", 1)[-1].strip()
                elif label in ("web", "website"):
                    link = paragraph.find("a", href=True)
                    result["website"] = link["href"] if link else paragraph.get_text(" ", strip=True).split(":", 1)[-1].strip(" -")
            match = re.search(r"\b(Sarajevo|Banja Luka|Mostar|Brčko|Tuzla|Zenica|Bijeljina|Trebinje|Vitez|Livno)\b", result["address"], re.I)
            result["city"] = match.group(1) if match else ""
            name = result["name"].lower()
            result["kind"] = "honorary" if "honorary" in name else "consulate" if "consulat" in name else "embassy" if "embassy" in name or "nunciature" in name else "other"
            result["verification"] = "resident" if result["city"] and ("bosnia" in result["address"].lower() or "herzegovina" in result["address"].lower()) else "needs_review"
        except Exception as exc:
            result["error"] = str(exc)[:300]
        results.append(result)
        print(f"{index}/{len(candidates)} {item['directory_title']}: {result['verification']}", flush=True)
        time.sleep(0.5)
output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {output_path}")
