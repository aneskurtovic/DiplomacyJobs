"""Conservative official-source ingestion. A link is a lead, never proof of a job."""
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import httpx
from bs4 import BeautifulSoup
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader
from io import BytesIO

from .models import Job, ScrapeRun, Source, SourceDocument

USER_AGENT = "DiplomacyJobs/0.1 (+official vacancy monitor; contact via site administrator)"
LOCATION = re.compile(r"\b(bosnia(?: and | & )herzegovina|bosna i hercegovina|sarajevo|banja luka|mostar|brčko|tuzla|zenica|bijeljina|trebinje)\b", re.I)
OUTSIDE = re.compile(r"\b(albania|chad|kosovo|montenegro|serbia|croatia|north macedonia|belgrade|zagreb|tirana|pristina)\b", re.I)
JOB_WORDS = re.compile(r"\b(vacan(?:cy|cies)|job|career|position|officer|assistant|adviser|advisor|traineeship|internship|consultant|oglas|konkurs|natječaj|posao|radno mjesto|slobodna radna mjesta|prijava|asistent|savjetnik)\b", re.I)
EXCLUDED = re.compile(r"\b(unpaid|volunteer|volont|scholarship|stipendij|grant|tender|procurement|nabavk|konkurs za projekte)\b", re.I)
DEADLINE = re.compile(r"(?:deadline|closing date|apply by|rok(?: za prijavu)?|prijave do|application deadline|najkasnije do)\D{0,35}(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-zčćšđž]+\s+\d{4})", re.I)
MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12, "januara": 1, "februara": 2, "marta": 3, "aprila": 4, "maja": 5, "juna": 6, "jula": 7, "augusta": 8, "septembra": 9, "oktobra": 10, "novembra": 11, "decembra": 12}


@dataclass
class Candidate:
    url: str
    title: str
    text: str
    city: str
    deadline: date | None
    content_hash: str
    location_evidence: str
    eligible: bool
    reason: str = ""


def canonicalize(url):
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.netloc:
        raise ValueError("Invalid source URL")
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", query, ""))


def trusted_host(host, domain):
    return host == domain or host.endswith("." + domain)


def parse_deadline(text):
    match = DEADLINE.search(text)
    if not match:
        return None
    value = match.group(1).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    words = value.lower().split()
    if len(words) == 3 and words[1].rstrip(".") in MONTHS:
        try:
            return date(int(words[2]), MONTHS[words[1].rstrip(".")], int(words[0]))
        except ValueError:
            pass
    return None


def fetch(client, url):
    response = client.get(url)
    response.raise_for_status()
    if len(response.content) > 5_000_000:
        raise ValueError("Document larger than 5 MB")
    content_type = response.headers.get("content-type", "").lower()
    final_host = urlsplit(str(response.url)).hostname or ""
    requested_host = urlsplit(url).hostname or ""
    if not trusted_host(final_host, requested_host):
        raise ValueError("Unexpected redirect host")
    if "pdf" in content_type or urlsplit(url).path.lower().endswith(".pdf"):
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages), None
    if "html" not in content_type:
        raise ValueError(f"Unsupported content type: {content_type}")
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(" ", strip=True), soup


def listing_links(source, soup):
    config = source.adapter_config or {}
    selector = config.get("link_selector", "a[href]")
    if not isinstance(selector, str) or len(selector) > 150:
        raise ValueError("Invalid link selector")
    links = []
    for link in soup.select(selector):
        href = link.get("href", "")
        title = link.get_text(" ", strip=True)
        if not href or not title or not JOB_WORDS.search(title):
            continue
        url = urljoin(source.url, href)
        if source.adapter == "eeas":
            if not trusted_host(urlsplit(url).hostname or "", "eeas.europa.eu") or "/delegations/bosnia-and-herzegovina/" not in urlsplit(url).path:
                continue
        elif source.adapter == "govuk":
            if not trusted_host(urlsplit(url).hostname or "", "tal.net"):
                continue
        else:
            host = urlsplit(source.url).hostname or ""
            if urlsplit(url).hostname != host:
                continue
            required_path = config.get("path_contains", "")
            if required_path and required_path not in urlsplit(url).path:
                continue
        links.append((canonicalize(url), title[:400]))
    links = list(dict.fromkeys(links))
    if len(links) > 500:
        raise ValueError("More than 500 links; configure source pagination")
    return links


def make_candidate(source, url, listing_title, text, soup):
    title = listing_title
    if soup:
        heading = soup.find("h1")
        if heading:
            title = heading.get_text(" ", strip=True)[:400] or title
    excerpt = LOCATION.search(text)
    city = ""
    if excerpt:
        city_match = re.search(r"\b(Sarajevo|Banja Luka|Mostar|Brčko|Tuzla|Zenica|Bijeljina|Trebinje)\b", text, re.I)
        city = city_match.group(1).title() if city_match else ""
    location_evidence = text[max(0, excerpt.start()-75):excerpt.end()+75] if excerpt else ""
    deadline = parse_deadline(text)
    today = timezone.localdate()
    job_like = bool(JOB_WORDS.search(title) and JOB_WORDS.search(text))
    in_country = bool(excerpt)
    excluded = bool(EXCLUDED.search(title) or re.search(r"\b(unpaid|neplaćen|volunteer|volont|scholarship|stipendij|grant|tender|procurement|nabavk)\b", text, re.I))
    # A global portal may mention BiH in navigation. Ambiguous pages go to review.
    outside = bool(OUTSIDE.search(location_evidence))
    fresh = bool(deadline and deadline >= today) or bool(not deadline and (source.adapter_config or {}).get("active_undated_listing"))
    eligible = job_like and in_country and not outside and not excluded and fresh
    reason = "" if eligible else "Nedovoljno dokaza o aktivnom oglasu, lokaciji ili vrsti angažmana"
    return Candidate(url, title, text[:100_000], city, deadline, hashlib.sha256(text.encode("utf-8")).hexdigest(), location_evidence, eligible, reason)


def ingest_source(source_id):
    source = Source.objects.select_related("organization").get(pk=source_id)
    if not source.enabled or source.adapter == "none":
        return None
    run = ScrapeRun.objects.create(source=source)
    now = timezone.now()
    source.last_attempt_at = now
    source.save(update_fields=["last_attempt_at"])
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True) as client:
            listing_text, soup = fetch(client, source.url)
            if soup is None:
                raise ValueError("Source listing must be HTML")
            links = listing_links(source, soup)
            if not links and not (source.adapter_config or {}).get("allow_empty", False):
                raise ValueError("No vacancy links matched; verify selector before treating as empty")
            candidates = []
            for url, title in links:
                try:
                    text, detail_soup = fetch(client, url)
                    candidates.append(make_candidate(source, url, title, text, detail_soup))
                except (httpx.HTTPError, ValueError) as exc:
                    raise ValueError(f"Vacancy detail failed: {url}: {exc}") from exc
        with transaction.atomic():
            seen = set()
            for candidate in candidates:
                seen.add(candidate.url)
                SourceDocument.objects.create(source=source, url=candidate.url, content_hash=candidate.content_hash, text=candidate.text)
                job, created = Job.objects.get_or_create(source=source, canonical_url=candidate.url, defaults={"title": candidate.title, "city": candidate.city, "deadline": candidate.deadline, "location_evidence": candidate.location_evidence, "status": "published" if candidate.eligible else "review", "content_hash": candidate.content_hash, "raw_text": candidate.text, "field_evidence": {"location": candidate.location_evidence, "review_reason": candidate.reason}, "last_checked_at": now})
                if not created:
                    protected = set(job.manually_edited_fields) | set(job.field_evidence.get("ai_fields", []))
                    for field, value in {"title": candidate.title, "city": candidate.city, "deadline": candidate.deadline, "location_evidence": candidate.location_evidence}.items():
                        if field not in protected:
                            setattr(job, field, value)
                    review_reason = candidate.reason
                    if job.content_hash != candidate.content_hash and job.field_evidence.get("ai_fields"):
                        job.status = "review"
                        review_reason = "Izvor je promijenjen nakon AI obrade"
                    job.content_hash = candidate.content_hash
                    job.raw_text = candidate.text
                    job.field_evidence = {**job.field_evidence, "location": candidate.location_evidence, "review_reason": review_reason}
                    job.last_seen_at = now
                    job.last_checked_at = now
                    job.missing_scans = 0
                    if candidate.eligible and job.status == "review" and not job.manually_edited_fields:
                        job.status = "published"
                    if not candidate.eligible and job.status == "published" and not job.last_reviewed_at:
                        job.status = "review"
                    job.save()
            for job in Job.objects.filter(source=source, status="published").exclude(canonical_url__in=seen):
                job.missing_scans += 1
                if job.missing_scans >= 2:
                    job.status = "closed"
                job.save(update_fields=["missing_scans", "status"])
            source.last_success_at = now
            source.consecutive_failures = 0
            source.status = "verified"
            source.save(update_fields=["last_success_at", "consecutive_failures", "status"])
            run.success = True
            run.candidates = len(candidates)
    except Exception as exc:
        source.consecutive_failures += 1
        if source.consecutive_failures >= 3:
            source.status = "failing"
        source.save(update_fields=["consecutive_failures", "status"])
        run.error = str(exc)[:2000]
    finally:
        run.finished_at = timezone.now()
        run.save()
    return run


def expire_jobs():
    now = timezone.now()
    today = timezone.localdate()
    Job.objects.filter(status="published", deadline__lt=today).update(status="closed")
    Job.objects.filter(status="published", deadline__isnull=True, first_seen_at__lt=now-timedelta(days=30), last_reviewed_at__isnull=True).update(status="closed")
    Job.objects.filter(status="published", deadline__isnull=True, first_seen_at__lt=now-timedelta(days=30), last_reviewed_at__lt=now-timedelta(days=30)).update(status="closed")
    SourceDocument.objects.filter(fetched_at__lt=now-timedelta(days=90)).delete()
