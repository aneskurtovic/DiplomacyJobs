"""Complete a server's certificate chain the way browsers do (AIA fetching), then verify it fully.

Some mission sites (kln.gov.my, mofa.gov.pk, sarajevo.embassy.qa) send only their leaf
certificate. Browsers download the missing intermediate from the "CA Issuers" URL inside
the leaf. This script does the same, then opens a normal TLS connection with verification,
hostname checking and full-chain building on (partial chains off), trusting only certifi's
roots. The fetched intermediates are never trust anchors.

Usage:
  python scripts/cert_chain.py HOST [HOST ...]          verify and print the chain
  python scripts/cert_chain.py HOST --save              also store data/intermediates/HOST.pem
  python scripts/cert_chain.py HOST --get URL [URL...]  fetch pages over the verified chain
"""
import argparse
import re
import ssl
import sys
import tempfile
from pathlib import Path

import certifi
import httpx

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "intermediates"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"


def decode(pem):
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as handle:
        handle.write(pem)
    try:
        return ssl._ssl._test_decode_cert(handle.name)
    finally:
        Path(handle.name).unlink()


def name(cert, field):
    return ", ".join(f"{k}={v}" for rdn in cert.get(field, ()) for k, v in rdn)


def as_pem(body):
    if body.lstrip().startswith(b"-----BEGIN CERTIFICATE-----"):
        return body.decode("ascii")
    return ssl.DER_cert_to_PEM_cert(body)


def root_names():
    """Common names of certifi's roots, from its "# Subject: CN=… O=…" comments."""
    text = Path(certifi.where()).read_text("utf-8")
    return {m.strip() for m in re.findall(r"^# Subject: CN=(.+?)(?: O=| OU=|$)", text, re.M)}


def common_name(cert, field):
    return next((v for rdn in cert.get(field, ()) for k, v in rdn if k == "commonName"), "")


def intermediates(host):
    """Follow CA Issuers links from the served leaf until a certifi root issues the last one.

    Only intermediates are returned. A self-signed certificate is never added, so trust
    anchors always come from certifi.
    """
    roots = root_names()
    pem = ssl.get_server_certificate((host, 443), timeout=20)
    cert = decode(pem)
    print(f"leaf    {name(cert, 'subject')}\n        issued by {name(cert, 'issuer')}")
    chain = []
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for _ in range(4):
            if common_name(cert, "issuer") in roots:
                print("        issuer is a certifi root")
                break
            urls = cert.get("caIssuers", ())
            if not urls:
                break
            # CA Issuers links are plain http by design; the verified handshake is what makes them safe.
            body = client.get(urls[0]).raise_for_status().content
            pem = as_pem(body)
            cert = decode(pem)
            if cert.get("subject") == cert.get("issuer"):
                raise ValueError(f"chain ends in a self-signed certificate certifi does not hold: {name(cert, 'subject')}")
            chain.append(pem)
            print(f"fetched {name(cert, 'subject')}\n        from {urls[0]}\n        issued by {name(cert, 'issuer')}")
    return chain


def context(chain):
    ctx = ssl.create_default_context(cafile=certifi.where())
    if chain:
        ctx.load_verify_locations(cadata="".join(chain))
    # A fetched intermediate must chain up to a certifi root; it may not end the chain itself.
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    return ctx


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("hosts", nargs="+")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--get", nargs="+", default=[])
    parser.add_argument("--links", default="", help="print hrefs whose URL or link text matches this regex instead of page text")
    parser.add_argument("--around", default="", help="print raw HTML around the first match of this regex")
    parser.add_argument("--browser", action="store_true", help="send a Chrome user agent (per-source impersonation)")
    args = parser.parse_args()
    ok = True
    for host in args.hosts:
        print(f"== {host}")
        try:
            chain = intermediates(host)
            ctx = context(chain)
            with httpx.Client(verify=ctx, timeout=25, follow_redirects=True, headers={"User-Agent": CHROME if args.browser else "Mozilla/5.0 (compatible; DiplomacyJobsBot/1.0)"}) as client:
                response = client.get(f"https://{host}/")
                print(f"verified handshake: HTTP {response.status_code} {response.url}")
                for url in args.get:
                    page = client.get(url)
                    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", page.text)))
                    print(f"-- GET {url}: HTTP {page.status_code} {page.url} {len(page.text)} chars")
                    if args.around and (hit := re.search(args.around, page.text, re.I)):
                        print(page.text[max(0, hit.start() - 2500):hit.end() + 800])
                    elif args.links:
                        for href, label in re.findall(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page.text):
                            label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", label)).strip()
                            if re.search(args.links, f"{href} {label}", re.I):
                                print(f"   {label[:80]!r} -> {href}")
                    else:
                        print(text[:3000])
            if args.save:
                STORE.mkdir(parents=True, exist_ok=True)
                (STORE / f"{host}.pem").write_text("".join(chain), "ascii")
                print(f"saved {STORE / f'{host}.pem'}")
        except Exception as exc:  # report every host
            ok = False
            print(f"FAILED: {type(exc).__name__}: {exc}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
