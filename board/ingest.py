"""Conservative official-source ingestion. A link is a lead, never proof of a job."""
import hashlib
import re
import ssl
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
TARGET_YEAR = 2026
MAX_DETAIL_LINKS = 100
MAX_LISTING_PAGES = 10
LOCATION = re.compile(r"\b(bosnia(?: and | & )herzegovina|bosna i hercegovina|sarajevo|banja luka|mostar|brčko|tuzla|zenica|bijeljina|trebinje)\b", re.I)
OUTSIDE = re.compile(r"\b(albania|chad|kosovo|montenegro|serbia|croatia|north macedonia|belgrade|zagreb|tirana|pristina)\b", re.I)
JOB_WORDS = re.compile(r"\b(vacan(?:cy|cies)|job|career|position|officer|assistant|adviser|advisor|traineeship|internship|consultant|oglas|konkurs|natječaj|posao|radno mjesto|slobodna radna mjesta|prijava|asistent|savjetnik|selezione|assunzione|impiegat[oi]|stellenangebot|stelle)\b", re.I)
EXCLUDED = re.compile(r"\b(unpaid|volunteer|volont|scholarship|stipendij|tender|call for proposals|poziv za projekte|javna nabavka)\b", re.I)
DATE_TEXT = r"\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-zčćšđž]{3,}\s+\d{4}|\b[A-Za-z]{3,}\s+\d{1,2},?\s+\d{4}"
DEADLINE = re.compile(r"(?:deadline|closing date|closing for applications?|posting end date|apply by|rok(?: za prijavu)?|prijave do|application deadline|najkasnije do|no later than|scad\.?(?: presentazione domande)?)\D{0,35}(" + DATE_TEXT + r")", re.I)
PUBLISHED = re.compile(r"(?:published|date of publication|issue date|data pubblicazione|datum objave|objavljeno)\D{0,20}(" + DATE_TEXT + r")", re.I)
MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12, "januara": 1, "februara": 2, "marta": 3, "aprila": 4, "maja": 5, "juna": 6, "jula": 7, "augusta": 8, "septembra": 9, "oktobra": 10, "novembra": 11, "decembra": 12}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())[:12]})


@dataclass
class Candidate:
    url: str
    title: str
    text: str
    city: str
    deadline: date | None
    source_published_at: date | None
    content_hash: str
    location_evidence: str
    eligibility: str
    eligible: bool
    in_scope_year: bool
    year_proven: bool
    reason: str = ""


def canonicalize(url):
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.netloc:
        raise ValueError("Invalid source URL")
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", query, ""))


def listing_link_in_scope(url, title):
    """Skip links in a clearly dated archive from another year.

    Undated links remain leads: their detail page must still prove a 2026 date.
    """
    archive_year = re.search(r"/(20\d{2})/(?:0?[1-9]|1[0-2])(?:/|$)", urlsplit(url).path)
    return not archive_year or int(archive_year.group(1)) == TARGET_YEAR


def trusted_host(host, domain):
    return host == domain or host.endswith("." + domain)


def parse_date(value):
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    words = value.lower().split()
    if len(words) == 3 and words[0].rstrip(".") in MONTHS:
        try:
            return date(int(words[2]), MONTHS[words[0].rstrip(".")], int(words[1].rstrip(",")))
        except ValueError:
            pass
    if len(words) == 3 and words[1].rstrip(".") in MONTHS:
        try:
            return date(int(words[2]), MONTHS[words[1].rstrip(".")], int(words[0]))
        except ValueError:
            pass
    return None


def parse_deadline(text):
    match = DEADLINE.search(text)
    return parse_date(match.group(1)) if match else None


def parse_published(text):
    match = PUBLISHED.search(text)
    return parse_date(match.group(1)) if match else None


def fetch(client, url):
    response = client.get(url)
    response.raise_for_status()
    # Bot challenges answer 202/204 with an empty body; that must not read as "no vacancies".
    if response.status_code != 200 or not response.content.strip():
        raise ValueError(f"Unusable response: HTTP {response.status_code}, {len(response.content)} bytes")
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
    if source.adapter == "osce":
        rows = soup.select(".job_list_row")
        if not rows:
            raise ValueError("OSCE job rows missing")
        result = []
        for row in rows:
            link = row.select_one("a.job_link[href]")
            if link and "BAH - OSCE Mission to Bosnia and Herzegovina" in row.get_text(" ", strip=True):
                result.append((canonicalize(link["href"]), link.get_text(" ", strip=True)[:400]))
        return result
    if source.adapter == "denmark" and "no current vacancies" in soup.get_text(" ", strip=True).lower():
        return []
    if source.adapter == "italy":
        section = soup.find(string=lambda value: value and "Bandi e selezioni aperti" in value)
        if not section:
            raise ValueError("Italian open-selections section missing")
        listing = section.parent.parent.find_next_sibling("ul")
        if listing is None:
            raise ValueError("Italian open-selections list missing")
        return [(canonicalize(urljoin(source.url, link["href"])), link.get_text(" ", strip=True)[:400]) for link in listing.find_all("a", href=True)]
    if source.adapter == "swiss":
        result = []
        for article in soup.select("article.article-print"):
            heading = article.find("h2")
            pdf = article.find("a", href=re.compile(r"\.pdf(?:\?|$)", re.I))
            if heading and pdf and JOB_WORDS.search(heading.get_text(" ", strip=True)):
                result.append((canonicalize(urljoin(source.url, pdf["href"])), heading.get_text(" ", strip=True)[:400]))
        return result
    if source.adapter == "eeas":
        return eeas_page_links(source, soup)
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
        if source.adapter == "govuk":
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
    return links


def eeas_page_links(source, soup):
    """Vacancy cards on one page of the EEAS listing filtered to BiH. Cards with a pre-2026 deadline are archive entries."""
    result = []
    for card in soup.select(".node--type-vacancy"):
        link = card.select_one(".card-title a[href]")
        if not link:
            raise ValueError("EEAS vacancy card without a title link")
        url = urljoin(source.url, link["href"])
        if not trusted_host(urlsplit(url).hostname or "", "eeas.europa.eu"):
            continue
        deadline = parse_date(next(iter(re.findall(r"\d{2}\.\d{2}\.\d{4}", card.get_text(" ", strip=True))), ""))
        if deadline and deadline.year < TARGET_YEAR:
            continue
        result.append((canonicalize(url), link.get_text(" ", strip=True)[:400]))
    return result


def us_date(value):
    try:
        return datetime.strptime(value.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def unct_page_links(source, soup, evidence):
    """Job cards on one page of the UN country team listing. Cards link to agency sites, so the card itself is the evidence."""
    result = []
    for card in soup.select("article.node--type-job-vacancy"):
        link = card.select_one("a[href]")
        if not link:
            raise ValueError("UN job card without a link")
        url = urljoin(source.url, link["href"])
        # Agencies with their own source (e.g. UNICEF) are skipped to avoid duplicate jobs.
        if urlsplit(url).scheme != "https" or urlsplit(url).hostname in (source.adapter_config or {}).get("skip_hosts", []):
            continue
        fields = [div.get_text(" ", strip=True) for div in card.select(".node__content > div > div")]
        published = parse_date(fields[0]) if fields else None
        card_text = card.get_text(" ", strip=True)
        deadline = parse_deadline(card_text)
        if deadline and deadline.year < TARGET_YEAR:
            continue
        url = canonicalize(url)
        evidence[url] = (f"Published {published.isoformat()}. " if published else "") + card_text
        result.append((url, link.get_text(" ", strip=True)[:400]))
    return result


def ohr_links(source, soup, evidence):
    """Every OHR section is either an explicit 'no active vacancy' note or a table; anything else means the page changed."""
    main = soup.select_one("main")
    headings = main.find_all("h4") if main else []
    if not headings:
        raise ValueError("OHR vacancy sections missing")
    result = []
    for heading in headings:
        block = heading.find_next_sibling(["p", "table"])
        if block is not None and block.name == "p" and "no active vacancy" in block.get_text(" ", strip=True).lower():
            continue
        if block is None or block.name != "table":
            raise ValueError(f"OHR section without vacancy table: {heading.get_text(' ', strip=True)}")
        for row in block.select("tbody tr"):
            cells = row.find_all("td")
            link = cells[0].find("a", href=True) if cells else None
            if len(cells) < 3 or not link:
                raise ValueError("OHR vacancy row changed shape")
            url = urljoin(source.url, link["href"])
            if not trusted_host(urlsplit(url).hostname or "", "ohr.int"):
                continue
            url = canonicalize(url)
            closing = us_date(cells[2].get_text(" ", strip=True))
            evidence[url] = f"{heading.get_text(' ', strip=True)}. Duty station: {cells[1].get_text(' ', strip=True)}." + (f" Closing date {closing.isoformat()}." if closing else "")
            result.append((url, link.get_text(" ", strip=True)[:400]))
    return result


def eufor_links(source, soup, evidence):
    """EUFOR lists local civilian hires as paragraphs linking a PDF job description, or says it has no vacancies."""
    block = soup.select_one(".category-desc")
    if block is None:
        raise ValueError("EUFOR vacancy block missing")
    result = []
    for paragraph in block.find_all("p"):
        link = paragraph.find("a", href=re.compile(r"\.pdf(?:\?|$)", re.I))
        if not link:
            continue
        text = paragraph.get_text(" ", strip=True)
        if not DEADLINE.search(text):
            raise ValueError(f"EUFOR vacancy without closing date: {text[:80]}")
        url = urljoin(source.url, link["href"])
        if not trusted_host(urlsplit(url).hostname or "", "euforbih.org"):
            continue
        url = canonicalize(url)
        evidence[url] = text
        result.append((url, link.get_text(" ", strip=True)[:400]))
    if not result and "do not have any vacancies" not in block.get_text(" ", strip=True).lower():
        raise ValueError("EUFOR page has neither vacancies nor a no-vacancies note")
    return result


def unicef_links(source, soup):
    """UNICEF careers keyword search. A 'More Jobs' control means the result set is truncated and coverage would be partial."""
    if soup.select_one(".more-link"):
        raise ValueError("UNICEF search results are paginated; narrow the search")
    result = []
    for link in soup.select("a.job-link[href]"):
        url = urljoin(source.url, link["href"])
        if urlsplit(url).hostname != "jobs.unicef.org" or not re.match(r"/en-us/job/\d+", urlsplit(url).path):
            continue
        result.append((canonicalize(url), link.get_text(" ", strip=True)[:400]))
    return list(dict.fromkeys(result))


def ebrd_links(source, soup):
    """EBRD SuccessFactors search. An unmatched location search falls back to the latest jobs worldwide, so rows are kept only by their BA location."""
    rows = soup.select("tr.data-row")
    if not rows and not soup.select_one("#searchresults, .searchResultsShell"):
        raise ValueError("EBRD search results missing")
    result = []
    for row in rows:
        link = row.select_one("a.jobTitle-link[href]")
        location = row.select_one("td.colLocation .jobLocation")
        if not link or not location:
            raise ValueError("EBRD result row changed shape")
        if not re.search(r",\s*BA$", location.get_text(" ", strip=True)):
            continue
        url = urljoin(source.url, link["href"])
        if urlsplit(url).hostname != "jobs.ebrd.com":
            continue
        result.append((canonicalize(url), link.get_text(" ", strip=True)[:400]))
    label = soup.select_one(".paginationLabel")
    total = re.search(r"of\s+(\d+)", label.get_text(" ", strip=True)) if label else None
    if result and len(result) == len(rows) and total and int(total.group(1)) > len(rows):
        raise ValueError("EBRD BiH results span several pages; add pagination")
    return result


def rcc_links(source, soup, evidence):
    """RCC Secretariat calls: cards with publication date and deadline; documentation is a ZIP, so the card is the evidence."""
    items = soup.select(".doc-item")
    if not items:
        if "there are currently no open vacancies" in soup.get_text(" ", strip=True).lower():
            return []
        raise ValueError("RCC page has neither vacancies nor a no-vacancies note")
    result = []
    for item in items:
        title = item.select_one(".title")
        link = item.find("a", href=re.compile(r"/vacancy_apps/|open_calls_zip"))
        if not title or not link:
            raise ValueError("RCC vacancy card changed shape")
        url = urljoin(source.url, link["href"])
        if not trusted_host(urlsplit(url).hostname or "", "rcc.int"):
            continue
        url = canonicalize(url)
        name = re.sub(r"^[\d-]+\s*(?:Terms of Reference\s*)?", "", title.get_text(" ", strip=True))
        text = item.get_text(" ", strip=True)
        # The Secretariat sits in Sarajevo; only its Brussels liaison office is elsewhere, and those cards go to review.
        if not re.search(r"brussels|liaison", text, re.I):
            text += " Duty station: Sarajevo (RCC Secretariat)."
        evidence[url] = text
        result.append((url, name[:400]))
    return result


# Listings whose card is the evidence: UN cards link to agency portals (several block bots), RCC links a ZIP.
CARD_EVIDENCE = {"unct", "rcc"}
PAGINATED = {"eeas": ".node--type-vacancy", "unct": "article.node--type-job-vacancy"}


def discover_links(client, source, soup, evidence=None):
    """Listing leads as (url, title). Adapters may add per-URL listing evidence (card text, closing dates) to `evidence`."""
    evidence = {} if evidence is None else evidence
    if source.adapter == "unct":
        if not soup.select_one(".view-jobs"):
            raise ValueError("UN jobs view missing")
        links = unct_page_links(source, soup, evidence)
    elif source.adapter == "ohr":
        return ohr_links(source, soup, evidence)
    elif source.adapter == "eufor":
        return eufor_links(source, soup, evidence)
    elif source.adapter == "unicef":
        return unicef_links(source, soup)
    elif source.adapter == "ebrd":
        return ebrd_links(source, soup)
    elif source.adapter == "rcc":
        return rcc_links(source, soup, evidence)
    else:
        links = listing_links(source, soup)
    if source.adapter == "eeas" and not soup.select(PAGINATED["eeas"]):
        raise ValueError("EEAS vacancy cards missing")
    if source.adapter in PAGINATED and soup.select(PAGINATED[source.adapter]):
        for page in range(1, MAX_LISTING_PAGES + 1):
            parts = urlsplit(source.url)
            query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "page"] + [("page", str(page))]
            _, page_soup = fetch(client, urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), "")))
            if page_soup is None or not page_soup.select(PAGINATED[source.adapter]):
                return list(dict.fromkeys(links))
            page_links = eeas_page_links(source, page_soup) if source.adapter == "eeas" else unct_page_links(source, page_soup, evidence)
            if page_links and set(page_links) <= set(links):
                # Some listings repeat the last page past the end.
                return list(dict.fromkeys(links))
            links += page_links
        raise ValueError(f"{source.adapter} listing exceeds {MAX_LISTING_PAGES} pages; check the BiH filter")
    return links


def make_candidate(source, url, listing_title, text, soup, listing_evidence=""):
    title = listing_title
    structured_published = None
    if source.adapter == "eeas" and soup:
        # Judge only the vacancy itself; site navigation mentions BiH and unrelated jobs.
        article = soup.select_one("article.node--type-vacancy")
        if article is None:
            raise ValueError("EEAS vacancy article missing")
        meta = soup.select_one(".content-header .node__meta")
        published_match = re.search(r"\d{2}\.\d{2}\.\d{4}", meta.get_text(" ", strip=True)) if meta else None
        structured_published = parse_date(published_match.group(0)) if published_match else None
        text = article.get_text(" ", strip=True)
    if source.adapter == "ohr" and soup:
        main = soup.select_one("main article")
        if main is None:
            raise ValueError("OHR post missing")
        date_tag = main.select_one(".date-publish")
        structured_published = us_date(date_tag.get_text(" ", strip=True)) if date_tag else None
        text = main.get_text(" ", strip=True)
    if source.adapter == "unicef" and soup:
        content = soup.select_one("#job-content")
        if content is None:
            raise ValueError("UNICEF job content missing")
        opened = soup.select_one(".open-date time[datetime]")
        structured_published = parse_date(opened["datetime"][:10]) if opened else None
        text = content.get_text(" ", strip=True)
    if source.adapter == "ebrd" and soup:
        description = soup.select_one(".jobdescription")
        if description is None:
            raise ValueError("EBRD job description missing")
        posted = soup.select_one("[itemprop=datePosted][content]")
        try:
            structured_published = datetime.strptime(posted["content"], "%a %b %d %H:%M:%S UTC %Y").date() if posted else None
        except ValueError:
            structured_published = None
        text = description.get_text(" ", strip=True)
    if listing_evidence:
        text = f"{listing_evidence} {text}"
    if soup:
        heading = soup.find("h1")
        # UNICEF's h1 is the generic "Current vacancies".
        if heading and source.adapter != "unicef":
            title = heading.get_text(" ", strip=True)[:400] or title
    excerpt = LOCATION.search(text)
    city = ""
    if excerpt:
        city_match = re.search(r"\b(Sarajevo|Banja Luka|Mostar|Brčko|Tuzla|Zenica|Bijeljina|Trebinje)\b", text, re.I)
        city = city_match.group(1).title() if city_match else ""
    location_evidence = text[max(0, excerpt.start()-75):excerpt.end()+75] if excerpt else ""
    deadline = parse_deadline(text) or parse_deadline(listing_title)
    published = structured_published or parse_published(text)
    today = timezone.localdate()
    job_like = bool(JOB_WORDS.search(title) and JOB_WORDS.search(text)) or bool(source.adapter == "osce" and "Requisition ID:" in text and "Closing Date:" in text) or source.adapter in ("eeas", "unct", "ohr", "eufor", "unicef", "ebrd", "rcc")
    in_country = bool(excerpt)
    excluded = bool(EXCLUDED.search(title) or re.search(r"\b(unpaid|neplaćen[aeo]?)\b", text, re.I))
    # A global portal may mention BiH in navigation. Ambiguous pages go to review.
    outside = bool(OUTSIDE.search(location_evidence))
    fresh = bool(deadline and deadline >= today) or bool(not deadline and (source.adapter_config or {}).get("active_undated_listing"))
    closed = "unfortunately, this position has been closed" in text.lower()
    eligible = job_like and in_country and not outside and not excluded and fresh and not closed
    eligibility = "Državljani i stalni rezidenti BiH ne ispunjavaju uslove za ovu međunarodnu poziciju." if source.adapter == "osce" and "nationals and permanent residents of the duty station are not eligible" in text.lower() else ""
    reason = "" if eligible else "Nedovoljno dokaza o aktivnom oglasu, lokaciji ili vrsti angažmana"
    path_year = re.search(r"/(20\d{2})/", urlsplit(url).path)
    if published:
        in_scope_year = published.year == TARGET_YEAR
        year_proven = in_scope_year
    elif path_year:
        in_scope_year = int(path_year.group(1)) == TARGET_YEAR
        year_proven = in_scope_year
    elif deadline:
        in_scope_year = deadline.year == TARGET_YEAR
        year_proven = False
    else:
        in_scope_year = False
        year_proven = False
    return Candidate(url, title, text[:100_000], city, deadline, published, hashlib.sha256(text.encode("utf-8")).hexdigest(), location_evidence, eligibility, eligible, in_scope_year, year_proven, reason)


def ingest_source(source_id):
    source = Source.objects.select_related("organization").get(pk=source_id)
    if not source.enabled or source.adapter == "none":
        return None
    run = ScrapeRun.objects.create(source=source)
    now = timezone.now()
    source.last_attempt_at = now
    source.save(update_fields=["last_attempt_at"])
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True, verify=ssl.create_default_context()) as client:
            listing_text, soup = fetch(client, source.url)
            if soup is None:
                raise ValueError("Source listing must be HTML")
            evidence = {}
            discovered_links = discover_links(client, source, soup, evidence)
            if not discovered_links and not (source.adapter_config or {}).get("allow_empty", False):
                raise ValueError("No vacancy links matched; verify selector before treating as empty")
            links = [(url, title) for url, title in discovered_links if listing_link_in_scope(url, title)]
            if (source.adapter_config or {}).get("partial_listing"):
                known = source.jobs.filter(status="published").values_list("canonical_url", "title")
                links = list(dict.fromkeys([*links, *known]))
            if len(links) > MAX_DETAIL_LINKS:
                raise ValueError(f"More than {MAX_DETAIL_LINKS} possible {TARGET_YEAR} vacancy links; narrow the source adapter")
            candidates = []
            for url, title in links:
                try:
                    if source.adapter in CARD_EVIDENCE:
                        candidate = make_candidate(source, url, title, evidence[url], None)
                    else:
                        text, detail_soup = fetch(client, url)
                        candidate = make_candidate(source, url, title, text, detail_soup, evidence.get(url, ""))
                    expired = bool(candidate.deadline and candidate.deadline < timezone.localdate())
                    # Already-expired vacancies are not worth a review entry; known jobs still refresh.
                    if candidate.in_scope_year and (not expired or source.jobs.filter(canonical_url=candidate.url).exists()):
                        candidates.append(candidate)
                except (httpx.HTTPError, ValueError) as exc:
                    raise ValueError(f"Vacancy detail failed: {url}: {exc}") from exc
        with transaction.atomic():
            seen = {url for url, _ in discovered_links}
            for candidate in candidates:
                SourceDocument.objects.create(source=source, url=candidate.url, content_hash=candidate.content_hash, text=candidate.text)
                job, created = Job.objects.get_or_create(source=source, canonical_url=candidate.url, defaults={"title": candidate.title, "city": candidate.city, "deadline": candidate.deadline, "source_published_at": candidate.source_published_at, "location_evidence": candidate.location_evidence, "eligibility": candidate.eligibility, "status": "published" if candidate.eligible and candidate.year_proven else "review", "content_hash": candidate.content_hash, "raw_text": candidate.text, "field_evidence": {"location": candidate.location_evidence, "review_reason": candidate.reason or ("Godina objave nije potvrđena" if not candidate.year_proven else "")}, "last_checked_at": now})
                if not created:
                    protected = set(job.manually_edited_fields) | set(job.field_evidence.get("ai_fields", []))
                    for field, value in {"title": candidate.title, "city": candidate.city, "deadline": candidate.deadline, "location_evidence": candidate.location_evidence, "eligibility": candidate.eligibility}.items():
                        if field not in protected:
                            setattr(job, field, value)
                    review_reason = candidate.reason or ("Godina objave nije potvrđena" if not candidate.year_proven else "")
                    if job.content_hash != candidate.content_hash and job.field_evidence.get("ai_fields"):
                        job.status = "review"
                        review_reason = "Izvor je promijenjen nakon AI obrade"
                    job.content_hash = candidate.content_hash
                    if "source_published_at" not in protected:
                        job.source_published_at = candidate.source_published_at
                    job.raw_text = candidate.text
                    job.field_evidence = {**job.field_evidence, "location": candidate.location_evidence, "review_reason": review_reason}
                    job.last_seen_at = now
                    job.last_checked_at = now
                    job.missing_scans = 0
                    if candidate.eligible and candidate.year_proven and job.status == "review" and not job.manually_edited_fields:
                        job.status = "published"
                    if not candidate.year_proven and job.status == "published" and not job.last_reviewed_at:
                        job.status = "review"
                    if not candidate.eligible and job.status == "published" and not job.last_reviewed_at:
                        job.status = "review"
                    job.save()
            if not (source.adapter_config or {}).get("partial_listing"):
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
