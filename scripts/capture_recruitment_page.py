"""Capture public recruitment responses for adapter development (TLS stays verified)."""
import argparse
from pathlib import Path
import httpx
from curl_cffi import requests

parser = argparse.ArgumentParser()
parser.add_argument("url")
parser.add_argument("output")
parser.add_argument("--chrome", action="store_true")
parser.add_argument("--turkish", action="store_true")
args = parser.parse_args()
if args.chrome:
    with requests.Session(impersonate="chrome", timeout=60) as client:
        if args.turkish:
            from urllib.parse import urljoin
            client.get(urljoin(args.url, "/Mission/ChangeLanguage?cultureCode=tr-TR&languageCode=50002"))
        response = client.get(args.url)
else:
    response = httpx.get(args.url, follow_redirects=True, timeout=60)
path = Path(args.output)
if not path.resolve().is_relative_to(Path("data/raw").resolve()):
    raise ValueError("Output must be under data/raw")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(response.content)
print(response.status_code, len(response.content), response.url, response.headers.get("content-type", ""))
