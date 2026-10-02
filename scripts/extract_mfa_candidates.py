"""Extract the ministry directory menu into a discovery queue, not verified employers."""
import json
import re
import sys
from pathlib import Path

directory_url = "https://mvp.gov.ba/en/embassies-in-bosnia-and-herzegovina"
html = Path(sys.argv[1]).read_text(encoding="utf-8")
unescaped = html.replace('\\"', '"')
entries = re.findall(r'\{"title":"([^"]+)","slug":"([^"]+)"\}', unescaped)
if not entries:
    raise SystemExit("No directory entries found; inspect the page structure")
result = [{"directory_title": title, "directory_slug": slug, "directory_url": directory_url, "verification": "pending"} for title, slug in dict.fromkeys(entries)]
Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Extracted {len(result)} candidates; residence and websites still require verification")
