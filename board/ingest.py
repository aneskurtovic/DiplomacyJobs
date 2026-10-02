"""Conservative official-source ingestion. A link is a lead, never proof of a job."""
import hashlib
import re
import ssl
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import httpx
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
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
EXCLUDED = re.compile(r"\b(unpaid|volunteer|volont\w*|scholarship|stipendij\w*|tender|call for proposals|poziv za projekte|javna nabavka)\b", re.I)
CONSULTANCY = re.compile(r"\b(consultan(?:t|cy|ts)|konsultant\w*|individual contractor|ic contract)\b", re.I)
INTERNSHIP = re.compile(r"\b(intern(?:ship)?s?|traineeships?|praksa|pripravni\w*|tirocinio)\b", re.I)
DATE_TEXT = r"\d{1,2}\.\s?\d{1,2}\.\s?\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}-[A-Za-z]{3}-\d{4}|\d{1,2}(?:\.|st|nd|rd|th)?\s+[A-Za-zčćšđž]{3,}\.?,?\s+\d{4}|\b[A-Za-z]{3,}\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*|\s+)\d{4}"
DEADLINE = re.compile(r"\b(?:deadline|closing date|closing for applications?|posting end date|apply by|rok\b(?: za prijavu)?|prijave do|application deadline|najkasnije do|no later than|scad\.?(?: presentazione domande)?)\D{0,45}(" + DATE_TEXT + r")", re.I)
# An extension notice names the date that counts now; the original deadline usually comes first in the text.
# It must name the deadline or the call itself, so a contract that "may be extended until" a later date does not count.
EXTENDED = re.compile(r"(?:\b(?:deadline|closing date|rok\w*|prijav\w*|applications?|vacancy|natje?čaj\w*|konkurs\w*|oglas\w*)\D{0,40}?(?:(?:" + DATE_TEXT + r")\W{0,5}(?:(?:is|has been|je)\s+)?)?\b(?:extended|prolonged|produžen\w*|produljen\w*)|\bextended (?:deadline|closing date)|\bprodužen\w* rok\w*)\D{0,30}(" + DATE_TEXT + r")", re.I)
PUBLISHED = re.compile(r"\b(?:published|date of publication|issue date|data pubblicazione|datum objave|objavljeno)\D{0,20}(" + DATE_TEXT + r")", re.I)
MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12, "januara": 1, "februara": 2, "marta": 3, "aprila": 4, "maja": 5, "juna": 6, "jula": 7, "augusta": 8, "septembra": 9, "oktobra": 10, "novembra": 11, "decembra": 12}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())[:12]})
MONTHS["sept"] = 9
# Croatian genitive month names.
MONTHS.update({name: number for number, name in enumerate(["siječnja", "veljače", "ožujka", "travnja", "svibnja", "lipnja", "srpnja", "kolovoza", "rujna", "listopada", "studenoga", "prosinca"], 1)} | {"studenog": 11})
# Bosnian nominative and Italian (Italian embassy pages) month names.
MONTHS.update({name: number for number, names in enumerate([("januar", "gennaio"), ("februar", "febbraio"), ("mart", "marzo"), ("april", "aprile"), ("maj", "maggio"), ("juni", "giugno"), ("juli", "luglio"), ("august", "agosto"), ("septembar", "settembre"), ("oktobar", "ottobre"), ("novembar", "novembre"), ("decembar", "dicembre")], 1) for name in names})


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
    excluded: bool = False
    opportunity_type: str = "employment"
    scope: str = ""
    withdrawn: bool = False


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
    value = value.strip().rstrip(".")
    compact = re.sub(r"\s+", "", value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(compact, fmt).date()
        except ValueError:
            pass
    words = [word.strip(".") for word in re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", value.lower()).replace(",", " ").replace("-", " ").split()]
    if len(words) != 3:
        return None
    day, month, year = (words[1], words[0], words[2]) if words[0] in MONTHS else (words[0], words[1], words[2])
    try:
        return date(int(year), MONTHS[month], int(day))
    except (KeyError, ValueError):
        return None


def first_date(pattern, text):
    """First match whose date actually parses; a garbled first hit must not hide a good second one."""
    return next((parsed for match in pattern.finditer(text) if (parsed := parse_date(match.group(1)))), None)


def parse_deadline(text):
    return first_date(EXTENDED, text) or first_date(DEADLINE, text)


def parse_published(text):
    return first_date(PUBLISHED, text)


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


def fetch_json(client, url, payload=None):
    response = client.get(url) if payload is None else client.post(url, json=payload)
    response.raise_for_status()
    if response.status_code != 200 or "json" not in response.headers.get("content-type", "").lower():
        raise ValueError(f"Unusable JSON response: HTTP {response.status_code}, {response.headers.get('content-type', '')}")
    if len(response.content) > 5_000_000:
        raise ValueError("Document larger than 5 MB")
    if urlsplit(str(response.url)).hostname != urlsplit(url).hostname:
        raise ValueError("Unexpected redirect host")
    return response.json()


def listing_links(source, soup):
    config = source.adapter_config or {}
    if source.adapter == "osce":
        rows = soup.select(".job_list_row")
        count = re.search(r"(\d+)\s+results?\b", soup.get_text(" ", strip=True))
        if count and int(count.group(1)) == 0:
            return []
        if not rows:
            raise ValueError("OSCE job rows missing")
        if count and int(count.group(1)) > len(rows):
            raise ValueError(f"OSCE search shows {len(rows)} of {count.group(1)} jobs; add pagination")
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
        # any_title: the path filter alone identifies vacancy pages, so titles like "Driver" still count.
        if not href or not title or not (config.get("any_title") or JOB_WORDS.search(title)):
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
    # The same vacancy is often linked twice ("Driver", "Read more"); the first anchor carries the title.
    first_titles = {}
    for url, title in links:
        first_titles.setdefault(url, title)
    links = list(first_titles.items())
    if not links and source.adapter == "denmark":
        raise ValueError("Danish vacancies page has neither vacancies nor its no-vacancies note")
    # empty_text: the page's own no-vacancies note; without it, an empty page means the layout changed.
    if not links and config.get("empty_text") and config["empty_text"].lower() not in soup.get_text(" ", strip=True).lower():
        raise ValueError("Listing has neither vacancy links nor its no-vacancies note")
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


def era_links(source, soup):
    """US State Department ERA vacancy search for the BiH mission. The record count must match the rows shown, or results are paginated."""
    count = re.search(r"(\d+)\s+records? found", soup.get_text(" ", strip=True))
    if not count:
        raise ValueError("ERA record count missing")
    result = []
    for link in soup.select('a[href*="viewVacancyDetail.hms"]'):
        url = urljoin(source.url, link["href"])
        params = dict(parse_qsl(urlsplit(url).query))
        if urlsplit(url).hostname != "erajobs.state.gov" or not params.get("jnum"):
            continue
        # _ref is a per-session token; jnum and orgId identify the vacancy.
        url = urlunsplit(("https", "erajobs.state.gov", urlsplit(url).path, urlencode({"jnum": params["jnum"], "orgId": params.get("orgId", "")}), ""))
        result.append((canonicalize(url), link.get_text(" ", strip=True)[:400]))
    result = list(dict.fromkeys(result))
    if len(result) != int(count.group(1)):
        raise ValueError(f"ERA shows {len(result)} of {count.group(1)} vacancies; add pagination")
    return result


def oracle_closing_date(value):
    """Oracle stores the posting office's end of day as the next morning in UTC (UNDP: 23:59 New York is 03:59Z)."""
    if not value:
        return None
    moment = datetime.fromisoformat(value)
    return (moment - timedelta(days=1)).date() if moment.hour < 12 else moment.date()


def oracle_links(client, source, evidence):
    """Oracle Recruiting Cloud (UNDP, IOM) public requisition API. Keyword search also matches descriptions, so only BiH duty stations are kept."""
    parts = urlsplit(source.url)
    site = re.search(r"/sites/([A-Za-z0-9_]+)/", parts.path)
    if parts.scheme != "https" or not site:
        raise ValueError("Oracle site number missing from source URL")
    api = f"https://{parts.hostname}/hcmRestApi/resources/latest"
    keyword = re.sub(r"[^A-Za-z]", "", (source.adapter_config or {}).get("keyword", "Bosnia"))
    items = fetch_json(client, f"{api}/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber={site.group(1)},keyword={keyword},limit={MAX_DETAIL_LINKS}").get("items") or []
    if len(items) != 1 or "TotalJobsCount" not in items[0]:
        raise ValueError("Oracle search response changed shape")
    requisitions = items[0].get("requisitionList") or []
    if items[0]["TotalJobsCount"] > len(requisitions):
        raise ValueError(f"Oracle search shows {len(requisitions)} of {items[0]['TotalJobsCount']} requisitions; add pagination")
    result = []
    for requisition in requisitions:
        if requisition.get("PrimaryLocationCountry") != "BA":
            continue
        number = re.sub(r"\D", "", str(requisition.get("Id", "")))
        details = fetch_json(client, f'{api}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id="{number}",siteNumber={site.group(1)}').get("items") or []
        if not number or len(details) != 1:
            raise ValueError(f"Oracle requisition {number} detail missing")
        detail = details[0]
        url = f"https://{parts.hostname}/hcmUI/CandidateExperience/en/sites/{site.group(1)}/job/{number}"
        published = (detail.get("ExternalPostedStartDate") or "")[:10]
        closing = oracle_closing_date(detail.get("ExternalPostedEndDate"))
        description = BeautifulSoup(detail.get("ExternalDescriptionStr") or "", "html.parser").get_text(" ", strip=True)
        # Agency, grade and contract type sit in flex fields, not in the description.
        flex = " ".join(f"{field['Prompt']}: {field['Value']}." for field in detail.get("requisitionFlexFields") or [] if field.get("Prompt") in ("Agency", "Grade", "Vacancy Type") and field.get("Value"))
        evidence[url] = f"{detail.get('Title', '')}. Location: {detail.get('PrimaryLocation', '')}. {flex} " + (f"Published {published}. " if published else "") + (f"Closing date {closing.isoformat()}. " if closing else "") + description
        result.append((url, (detail.get("Title") or requisition.get("Title") or "")[:400]))
    return result


def workday_links(client, source, evidence):
    """Workday career site JSON API (UNHCR). The country facet lists every country with an open posting, so no BiH entry means no BiH jobs."""
    parts = urlsplit(source.url)
    site = parts.path.strip("/").split("/")[-1]
    if parts.scheme != "https" or not (parts.hostname or "").endswith(".myworkdayjobs.com") or not re.fullmatch(r"[A-Za-z0-9_-]+", site):
        raise ValueError("Workday site missing from source URL")
    api = f"https://{parts.hostname}/wday/cxs/{parts.hostname.split('.')[0]}/{site}"
    search = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
    facets = {facet.get("facetParameter"): facet for group in fetch_json(client, f"{api}/jobs", search).get("facets", []) for facet in [group, *group.get("values", [])] if isinstance(facet, dict)}
    if "locationCountry" not in facets:
        raise ValueError("Workday country facet missing")
    country = next((value["id"] for value in facets["locationCountry"].get("values", []) if value.get("descriptor") == "Bosnia and Herzegovina"), None)
    if country is None:
        return []
    search["appliedFacets"] = {"locationCountry": [country]}
    page = fetch_json(client, f"{api}/jobs", search)
    postings = page.get("jobPostings", [])
    if page.get("total", 0) > len(postings):
        raise ValueError(f"Workday shows {len(postings)} of {page.get('total')} BiH postings; add pagination")
    result = []
    for posting in postings:
        path = posting.get("externalPath", "")
        if not path.startswith("/job/"):
            raise ValueError("Workday posting without a job path")
        detail = fetch_json(client, f"{api}{path}").get("jobPostingInfo") or {}
        url = detail.get("externalUrl", "")
        if (detail.get("jobRequisitionLocation") or {}).get("country", {}).get("alpha2Code") != "BA" or urlsplit(url).hostname != parts.hostname:
            continue
        description = BeautifulSoup(detail.get("jobDescription") or "", "html.parser").get_text(" ", strip=True)
        opened, ends = parse_date(detail.get("startDate") or ""), parse_date(detail.get("endDate") or "")
        # endDate is when the posting is taken down, often the day after the stated deadline.
        stated = parse_deadline(description)
        closing = stated if stated and opened and ends and opened <= stated <= ends else ends
        evidence[canonicalize(url)] = f"{detail.get('title', '')}. Location: {detail.get('location', '')} ({detail['jobRequisitionLocation']['country'].get('descriptor', '')}). " + (f"Published {opened.isoformat()}. " if opened else "") + (f"Closing date {closing.isoformat()}. " if closing else "") + description
        result.append((canonicalize(url), (detail.get("title") or posting.get("title") or "")[:400]))
    return result


def csod_links(client, source, evidence):
    """Cornerstone career site (World Bank Group). The page hands every visitor an anonymous token for its own job search API; keyword search ignores locations, so all postings are read and kept by country BA."""
    parts = urlsplit(source.url)
    site = re.search(r"/careersite/(\d+)/", parts.path)
    if parts.scheme != "https" or not (parts.hostname or "").endswith(".csod.com") or not site:
        raise ValueError("Cornerstone career site missing from source URL")
    response = client.get(source.url)
    response.raise_for_status()
    token, cloud = re.search(r'"token"\s*:\s*"([^"]+)"', response.text), re.search(r'"cloud"\s*:\s*"(https://[a-z0-9.-]+\.csod\.com)/?"', response.text)
    if not token or not cloud:
        raise ValueError("Cornerstone search token missing")
    headers = {"Authorization": f"Bearer {token.group(1)}"}
    postings, page, total = [], 1, None
    while page <= 10:
        body = {"careerSiteId": int(site.group(1)), "careerSitePageId": int(site.group(1)), "pageNumber": page, "pageSize": 100, "cultureId": 1, "searchText": "", "cultureName": "en-US", "states": [], "countryCodes": [], "cities": [], "placeID": "", "radius": None, "postingsWithinDays": None, "customFieldCheckboxKeys": [], "customFieldDropdowns": [], "customFieldRadios": []}
        reply = client.post(f"{cloud.group(1)}/rec-job-search/external/jobs", json=body, headers=headers)
        reply.raise_for_status()
        data = reply.json().get("data") or {}
        if "totalCount" not in data:
            raise ValueError("Cornerstone search response changed shape")
        total = data["totalCount"]
        postings += data.get("requisitions") or []
        if not data.get("requisitions") or len(postings) >= total:
            break
        page += 1
    if len(postings) < (total or 0):
        raise ValueError(f"Cornerstone search shows {len(postings)} of {total} postings")
    result = []
    for posting in postings:
        places = [place for place in posting.get("locations") or [] if place.get("country") == "BA"]
        if not places:
            continue
        url = f"https://{parts.hostname}/ux/ats/careersite/{site.group(1)}/home/requisition/{int(posting['requisitionId'])}?c={dict(parse_qsl(parts.query)).get('c', '')}"
        opened, closing = us_date(posting.get("postingEffectiveDate") or ""), us_date(posting.get("postingExpirationDate") or "")
        description = BeautifulSoup(posting.get("externalDescription") or "", "html.parser").get_text(" ", strip=True)
        evidence[url] = f"{posting.get('displayJobTitle', '')}. Location: {', '.join(place.get('city', '') for place in places)}, Bosnia and Herzegovina. " + (f"Published {opened.isoformat()}. " if opened else "") + (f"Closing date {closing.isoformat()}. " if closing else "") + description
        result.append((url, (posting.get("displayJobTitle") or "")[:400]))
    return result


UN_BIH_STATIONS = {"SARAJEVO", "BANJA LUKA", "MOSTAR", "TUZLA", "BRCKO", "BRČKO", "BIHAC", "BIHAĆ", "ZENICA"}


def uncareers_links(client, source, evidence):
    """UN Secretariat careers (careers.un.org) public API. Keyword search also hits descriptions, so every opening is paged through and kept by its BiH duty station."""
    api = "https://careers.un.org/api/public/opening/jo/list/filteredV2/en"
    openings, page, count = {}, 0, None
    while page < 20:
        data = fetch_json(client, api, {"filterConfig": {}, "pagination": {"page": page, "itemPerPage": 100, "sortBy": "startDate", "sortDirection": -1}}).get("data") or {}
        if "count" not in data or not isinstance(data.get("list"), list):
            raise ValueError("UN careers response changed shape")
        count = data["count"]
        for opening in data["list"]:
            openings[int(opening["jobId"])] = opening
        if not data["list"] or len(openings) >= count:
            break
        page += 1
    if len(openings) < count:
        raise ValueError(f"UN careers lists {count} openings; more than the pages read")
    result = []
    for job_id, opening in openings.items():
        stations = [station.get("description", "") for station in opening.get("dutyStation") or []]
        if not any(station.upper() in UN_BIH_STATIONS for station in stations):
            continue
        url = f"https://careers.un.org/jobSearchDescription/{job_id}?language=en"
        opened = (opening.get("startDate") or "")[:10]
        closing = oracle_closing_date((opening.get("endDate") or "").replace("Z", "+00:00"))
        description = BeautifulSoup(opening.get("jobDescription") or "", "html.parser").get_text(" ", strip=True)
        department = (opening.get("dept") or {}).get("name", "")
        evidence[url] = f"{opening.get('postingTitle', '')}. Location: {', '.join(stations).title()}, Bosnia and Herzegovina. Department: {department}. Grade: {opening.get('jobLevel', '')}. " + (f"Published {opened}. " if opened else "") + (f"Closing date {closing.isoformat()}. " if closing else "") + description
        result.append((url, (opening.get("postingTitle") or opening.get("jobTitle") or "")[:400]))
    return result


def coe_links(client, source, soup):
    """Council of Europe talent marketplace (Avature). Six cards per page; the stated result count must be reached, and only BiH duty stations are kept."""
    total = re.search(r"(\d+)\s+results?\b", soup.get_text(" ", strip=True))
    if not total:
        raise ValueError("CoE result count missing")
    cards, page = [], soup
    while True:
        page_cards = page.select("article.article--result")
        if not page_cards:
            break
        cards += page_cards
        if len(cards) >= int(total.group(1)) or len(cards) > MAX_DETAIL_LINKS:
            break
        parts = urlsplit(source.url)
        _, page = fetch(client, urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode({"jobOffset": len(cards)}), "")))
        if page is None:
            break
    if len(cards) != int(total.group(1)):
        raise ValueError(f"CoE shows {len(cards)} of {total.group(1)} vacancies")
    result = []
    for card in cards:
        link = card.select_one("h3 a[href*='/JobDetail/']")
        station = card.select_one(".list-item-dutyStation")
        if not link or not station:
            raise ValueError("CoE vacancy card changed shape")
        url = urljoin(source.url, link["href"])
        if LOCATION.search(station.get_text(" ", strip=True)) and urlsplit(url).hostname == "talents.coe.int":
            result.append((canonicalize(url), link.get_text(" ", strip=True)[:400]))
    return result


def coe_fields(soup):
    fields = {}
    for field in soup.select(".article__content__view__field"):
        label, value = field.select_one(".article__content__view__field__label"), field.select_one(".article__content__view__field__value")
        if label and value:
            fields[label.get_text(" ", strip=True)] = value.get_text(" ", strip=True)
    return fields


def coe_date(value):
    try:
        return datetime.strptime(value or "", "%d-%b-%Y").date()
    except ValueError:
        return None


# Listings whose card is the evidence: UN cards link to agency portals (several block bots), RCC links a ZIP, Oracle and Workday are JSON APIs.
CARD_EVIDENCE = {"unct", "rcc", "oracle", "workday", "uncareers", "csod"}
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
    elif source.adapter == "era":
        return era_links(source, soup)
    elif source.adapter == "oracle":
        return oracle_links(client, source, evidence)
    elif source.adapter == "workday":
        return workday_links(client, source, evidence)
    elif source.adapter == "coe":
        return coe_links(client, source, soup)
    elif source.adapter == "uncareers":
        return uncareers_links(client, source, evidence)
    elif source.adapter == "csod":
        return csod_links(client, source, evidence)
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


def opportunity_type(title):
    """Judged from the title only; descriptions mention consultants and interns in passing."""
    if CONSULTANCY.search(title):
        return "consultancy"
    if INTERNSHIP.search(title):
        return "paid_internship"
    return "employment"


NATIONAL = re.compile(r"\b(national (?:post|position|consultant|personnel|officer|professional)|npsa|no[a-d]|g-?[1-7]|gs-?[1-7]|lch-?\d|local agent|local staff|locally engaged)\b|external recruitment \(local\)", re.I)
INTERNATIONAL = re.compile(r"\b(international (?:consultant|position|post|recruitment|staff)|ipsa|p-?[1-5]|secondment|seconded)\b|external recruitment \(international\)|(?<!\w)(?-i:\(S\d?\))", re.I)


def recruitment_scope(title, text):
    """National or international post, from explicit grade or recruitment markers near the top. Mixed or missing evidence stays unknown. ERA only hosts locally employed staff vacancies, so its jobs are national."""
    for evidence in (title, text[:800]):
        national, international = bool(NATIONAL.search(evidence)), bool(INTERNATIONAL.search(evidence))
        if national != international:
            return "national" if national else "international"
        if national:
            return ""
    return ""


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
    if source.adapter == "era" and soup:
        period = re.search(r"Open Period:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
        if period is None:
            raise ValueError("ERA open period missing")
        structured_published = us_date(period.group(1))
        closing = us_date(period.group(2))
        text = (f"Closing date {closing.isoformat()}. " if closing else "") + text
    config = source.adapter_config or {}
    if source.adapter == "generic" and soup:
        # content_selector judges only the article, not site navigation; published_selector names the element holding the publication date.
        content = soup.select_one(config["content_selector"]) if config.get("content_selector") else None
        if config.get("content_selector") and content is None:
            raise ValueError("Vacancy content element missing")
        if content is not None:
            text = content.get_text(" ", strip=True)
        stamp = soup.select_one(config["published_selector"]) if config.get("published_selector") else None
        structured_published = parse_date(stamp.get_text(" ", strip=True)) if stamp else None
    if source.adapter == "coe" and soup:
        fields = coe_fields(soup)
        if not fields.get("Duty station"):
            raise ValueError("CoE vacancy fields missing")
        structured_published = coe_date(fields.get("Posted date"))
        closing = coe_date(fields.get("Deadline to apply"))
        text = f"Duty station: {fields['Duty station']}. " + (f"Closing date {closing.isoformat()}. " if closing else "") + " ".join(f"{label}: {value}" for label, value in fields.items())
    if source.adapter == "japan" and soup:
        # The publication date sits right under the h1 as YYYY/M/D; it is the page's only date in that form.
        stamp = re.search(r"\b(20\d{2})/(\d{1,2})/(\d{1,2})\b", text)
        structured_published = date(*map(int, stamp.groups())) if stamp else None
    if listing_evidence:
        text = f"{listing_evidence} {text}"
    if soup:
        heading = soup.find("h1")
        # UNICEF's h1 is the generic "Current vacancies"; ERA's is the State Department banner.
        if heading and source.adapter not in ("unicef", "era"):
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
    job_like = bool((JOB_WORDS.search(title) or (source.adapter_config or {}).get("any_title")) and JOB_WORDS.search(text)) or bool(source.adapter == "osce" and "Requisition ID:" in text and "Closing Date:" in text) or source.adapter in ("eeas", "unct", "ohr", "eufor", "unicef", "ebrd", "rcc", "era", "oracle", "workday", "coe", "uncareers", "csod")
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
        # A late-2026 posting may close in 2027; without a publication date it still goes to review.
        in_scope_year = deadline.year >= TARGET_YEAR
        year_proven = False
    else:
        in_scope_year = False
        year_proven = False
    return Candidate(url, title, text[:100_000], city, deadline, published, hashlib.sha256(text.encode("utf-8")).hexdigest(), location_evidence, eligibility, eligible, in_scope_year, year_proven, reason, excluded, opportunity_type(title), "national" if source.adapter == "era" else recruitment_scope(title, text), closed)


FETCH_ERRORS = (httpx.HTTPError, curl_requests.RequestsError, ValueError)
AI_CHANGED = "Izvor je promijenjen nakon AI obrade"
REOPENABLE = ("deadline", "missing")


def open_client(source):
    """Sites that refuse non-browser TLS fingerprints opt in with adapter_config.impersonate."""
    if (source.adapter_config or {}).get("impersonate"):
        return curl_requests.Session(impersonate="chrome", timeout=20, allow_redirects=True)
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True, verify=ssl.create_default_context())


def ingest_source(source_id):
    source = Source.objects.select_related("organization").get(pk=source_id)
    if not source.enabled or source.adapter == "none":
        return None
    # The file lock is per container; an overlapping run elsewhere would count every job as missing twice.
    if source.runs.filter(finished_at__isnull=True, started_at__gte=timezone.now() - timedelta(hours=1)).exists():
        return None
    run = ScrapeRun.objects.create(source=source)
    now = timezone.now()
    source.last_attempt_at = now
    source.save(update_fields=["last_attempt_at"])
    try:
        with open_client(source) as client:
            listing_text, soup = fetch(client, source.url)
            if soup is None:
                raise ValueError("Source listing must be HTML")
            evidence = {}
            discovered_links = discover_links(client, source, soup, evidence)
            if not discovered_links and not (source.adapter_config or {}).get("allow_empty", False):
                raise ValueError("No vacancy links matched; verify selector before treating as empty")
            # Without a no-vacancies note or a result count, an empty listing may be a changed layout; it must not close live jobs.
            unconfirmed_empty = source.adapter in ("generic", "japan", "swiss") and not (source.adapter_config or {}).get("empty_text")
            if not discovered_links and unconfirmed_empty and source.jobs.filter(status="published").exists():
                raise ValueError("Listing is suddenly empty while jobs are published; verify the page before treating it as empty")
            # URL columns hold 1000 characters; on PostgreSQL a longer one would roll back the whole source.
            links = [(url, title) for url, title in discovered_links if listing_link_in_scope(url, title) and len(url) <= 1000]
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
                    skip_if_new = candidate.excluded or candidate.withdrawn or bool(candidate.deadline and candidate.deadline < timezone.localdate())
                    # Expired, withdrawn and excluded leads are not worth a review entry; known jobs always refresh, even when their deadline moved into 2027.
                    if source.jobs.filter(canonical_url=candidate.url).exists() or (candidate.in_scope_year and not skip_if_new):
                        candidates.append(candidate)
                except FETCH_ERRORS as exc:
                    raise ValueError(f"Vacancy detail failed: {url}: {exc}") from exc
        with transaction.atomic():
            seen = {url for url, _ in discovered_links}
            for candidate in candidates:
                # A snapshot is kept per change, not per scan; unchanged pages would store the same text every day.
                latest = SourceDocument.objects.filter(source=source, url=candidate.url).order_by("-fetched_at").values_list("content_hash", flat=True).first()
                if latest != candidate.content_hash:
                    SourceDocument.objects.create(source=source, url=candidate.url, content_hash=candidate.content_hash, text=candidate.text)
                job, created = Job.objects.get_or_create(source=source, canonical_url=candidate.url, defaults={"title": candidate.title, "city": candidate.city, "deadline": candidate.deadline, "source_published_at": candidate.source_published_at, "opportunity_type": candidate.opportunity_type, "scope": candidate.scope, "location_evidence": candidate.location_evidence, "eligibility": candidate.eligibility, "status": "published" if candidate.eligible and candidate.year_proven else "review", "content_hash": candidate.content_hash, "raw_text": candidate.text, "field_evidence": {"location": candidate.location_evidence, "review_reason": candidate.reason or ("Godina objave nije potvrđena" if not candidate.year_proven else "")}, "last_checked_at": now})
                if not created:
                    protected = set(job.manually_edited_fields) | set(job.field_evidence.get("ai_fields", []))
                    for field, value in {"title": candidate.title, "city": candidate.city, "deadline": candidate.deadline, "opportunity_type": candidate.opportunity_type, "scope": candidate.scope, "location_evidence": candidate.location_evidence, "eligibility": candidate.eligibility}.items():
                        if field not in protected:
                            setattr(job, field, value)
                    review_reason = candidate.reason or ("Godina objave nije potvrđena" if not candidate.year_proven else "")
                    # A source change after AI enrichment waits for a human, also on later unchanged scans.
                    source_changed = job.content_hash != candidate.content_hash
                    ai_changed = bool(job.field_evidence.get("ai_fields")) and (job.content_hash != candidate.content_hash or (job.status == "review" and job.field_evidence.get("review_reason") == AI_CHANGED))
                    expired = bool(job.deadline and job.deadline < timezone.localdate())
                    # An extended deadline or a job back on the listing reopens it; human and stale closures stay.
                    if job.status == "closed" and job.closed_reason in REOPENABLE and not expired:
                        job.status, job.closed_reason = "review", ""
                    if ai_changed and job.status != "closed":
                        job.status = "review"
                        review_reason = AI_CHANGED
                    job.content_hash = candidate.content_hash
                    if "source_published_at" not in protected:
                        job.source_published_at = candidate.source_published_at
                    job.raw_text = candidate.text
                    job.field_evidence = {**job.field_evidence, "location": candidate.location_evidence, "review_reason": review_reason}
                    job.last_seen_at = now
                    job.last_checked_at = now
                    job.missing_scans = 0
                    if candidate.eligible and candidate.year_proven and job.status == "review" and not job.manually_edited_fields and not ai_changed:
                        job.status = "published"
                    if not candidate.year_proven and job.status == "published" and not job.last_reviewed_at:
                        job.status = "review"
                    if not candidate.eligible and job.status == "published" and not job.last_reviewed_at:
                        job.status = "review"
                    # A reviewed job is trusted until its source changes and it no longer qualifies.
                    if not candidate.eligible and job.status == "published" and job.last_reviewed_at and source_changed:
                        job.status = "review"
                    if expired and job.status != "closed":
                        job.status, job.closed_reason = "closed", "deadline"
                    if candidate.withdrawn and job.status != "closed":
                        job.status, job.closed_reason = "closed", "withdrawn"
                    job.save()
            if not (source.adapter_config or {}).get("partial_listing"):
                for job in Job.objects.filter(source=source, status__in=("published", "review")).exclude(canonical_url__in=seen):
                    job.missing_scans += 1
                    if job.missing_scans >= 2:
                        job.status, job.closed_reason = "closed", "missing"
                    job.save(update_fields=["missing_scans", "status", "closed_reason"])
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
    Job.objects.filter(status__in=("published", "review"), deadline__lt=today).update(status="closed", closed_reason="deadline")
    Job.objects.filter(status="published", deadline__isnull=True, first_seen_at__lt=now-timedelta(days=30), last_reviewed_at__isnull=True).update(status="closed", closed_reason="stale")
    Job.objects.filter(status="published", deadline__isnull=True, first_seen_at__lt=now-timedelta(days=30), last_reviewed_at__lt=now-timedelta(days=30)).update(status="closed", closed_reason="stale")
    # Undated leads nobody reviewed in two months are not worth keeping in the queue.
    Job.objects.filter(status="review", deadline__isnull=True, first_seen_at__lt=now-timedelta(days=60)).update(status="closed", closed_reason="stale")
    SourceDocument.objects.filter(fetched_at__lt=now-timedelta(days=90)).delete()
    ScrapeRun.objects.filter(started_at__lt=now-timedelta(days=365)).delete()
