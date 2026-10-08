"""Public, country-filtered aggregator listings; dates and employers stay attributed."""
import hashlib
import re
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from django.utils import timezone

from . import ingest as core


def reliefweb_feed(source):
    """ReliefWeb's country RSS feed: served where the HTML river is behind a challenge, and it carries the whole advert."""
    return source.adapter == "reliefweb" and urlsplit(source.url).path == "/jobs/rss.xml"


# The unfiltered feed stops at 20 items, so a country feed that full may be cut short.
RELIEFWEB_FEED_LIMIT = 20


def reliefweb_feed_links(client, source, evidence):
    response = core.request(client, "get", source.url)
    response.raise_for_status()
    # A bot challenge answers 202 with an HTML page.
    if response.status_code != 200 or "xml" not in response.headers.get("content-type", "").lower():
        raise ValueError(f"ReliefWeb feed unusable: HTTP {response.status_code}, {response.headers.get('content-type', '')}")
    channel = core.ElementTree.fromstring(response.content).find("channel")
    if channel is None:
        raise ValueError("ReliefWeb feed changed shape")
    items = channel.findall("item")
    if len(items) >= RELIEFWEB_FEED_LIMIT:
        raise ValueError(f"ReliefWeb feed has {len(items)} items; it may be truncated")
    links = {}
    for item in items:
        url = core.canonicalize((item.findtext("link") or "").strip())
        title = (item.findtext("title") or "").strip()
        if urlsplit(url).hostname != "reliefweb.int" or not re.fullmatch(r"/job/\d+/[^/]+/?", urlsplit(url).path):
            raise ValueError("Unexpected aggregator vacancy link")
        if not title:
            raise ValueError("Vacancy title missing")
        evidence[url] = item
        links[url] = title
    return list(links.items())


def listing_links(client, source, soup, evidence):
    if reliefweb_feed(source):
        return reliefweb_feed_links(client, source, evidence)
    links = {}
    expected = None
    for page in range(core.MAX_LISTING_PAGES):
        if source.adapter == "reliefweb":
            counter = soup.select_one(".rw-river-results")
            match = re.search(r"of\s+([\d,]+)\s+results|\b(0)\s+results", counter.get_text(" ", strip=True), re.I) if counter else None
            cards = soup.select("article.rw-river-article--job .rw-river-article__title a[href]")
            pattern = r"/job/\d+/[^/]+/?"
        else:
            counter = soup.select_one(".results-notice")
            match = re.search(r"([\d,]+)\s+jobs?\s+match", counter.get_text(" ", strip=True), re.I) if counter else None
            cards = soup.select("#search_results .job a[href]")
            pattern = r"/jobs/\d+/?"
        if not match:
            raise ValueError(f"{source.adapter}: result count missing; cannot confirm an empty listing")
        total = int(next(value for value in match.groups() if value is not None).replace(",", ""))
        if expected is not None and total != expected:
            raise ValueError("Listing changed during pagination; retry without closing jobs")
        expected = total
        if total > core.MAX_DETAIL_LINKS:
            raise ValueError("Aggregator result limit exceeded; narrow the country filter")
        before = len(links)
        for card in cards:
            url = core.canonicalize(urljoin(source.url, card["href"]))
            if urlsplit(url).hostname != urlsplit(source.url).hostname or not re.fullmatch(pattern, urlsplit(url).path):
                raise ValueError("Unexpected aggregator vacancy link")
            heading = card.find("h3") if source.adapter == "impactpool" else card
            title = heading.get_text(" ", strip=True) if heading else ""
            if not title:
                raise ValueError("Vacancy title missing")
            links[url] = title
        if len(links) == total:
            return list(links.items())
        if len(links) > total or len(links) == before:
            raise ValueError("Incomplete or repeated aggregator listing; no jobs will be closed")
        # Public HTML pagination. If a portal changes to a different loading
        # protocol, count/repetition validation fails instead of silently truncating.
        parts = urlsplit(source.url)
        params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
        params.append(("page", str(page + (1 if source.adapter == "reliefweb" else 2))))
        _, soup = core.fetch(client, urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), "")))
        if soup is None:
            raise ValueError("Aggregator listing must be HTML")
    raise ValueError("Aggregator pagination limit exceeded")


def safe_url(value):
    parts = urlsplit(value)
    return core.canonicalize(value) if parts.scheme in ("http", "https") and parts.hostname and not parts.username and not parts.password and len(value) <= 1000 else ""


def impactpool_application(client, url):
    # Read only the public redirect, without visiting or submitting the application.
    response = core.request(client, "get", url.rstrip("/") + "/apply", follow_redirects=False)
    if response.status_code in (301, 302, 303, 307, 308):
        target = safe_url(urljoin(url, response.headers.get("location", "")))
        if target and urlsplit(target).hostname not in {"www.impactpool.org", "impactpool.org"}:
            return target
    response.raise_for_status()
    return ""  # Login walls or a form are not an original employer URL.


def reliefweb_page(url, soup):
    """Title, employer, body text, dates, countries, whether BiH is tagged, and apply links from a ReliefWeb job page."""
    article = soup.select_one("article.node--job")
    heading = article.select_one("h1") if article else None
    body = article.select_one(".rw-article__content") if article else None
    employer = article.select_one(".rw-article__header .rw-entity-meta__tag-value--source") if article else None
    posted = article.select_one(".rw-entity-meta__tag-value--posted time[datetime]") if article else None
    closing = article.select_one(".rw-entity-meta__tag-value--closing time[datetime]") if article else None
    countries = article.select("#details .rw-entity-meta__tag-value--country a") if article else []
    if not all((heading, body, employer, posted, closing, countries)):
        raise ValueError("ReliefWeb job fields missing")
    return (heading.get_text(" ", strip=True), employer.get_text(" ", strip=True), body.get_text(" ", strip=True),
            core.parse_date(posted["datetime"][:10]), core.parse_date(closing["datetime"][:10]),
            [country.get_text(" ", strip=True) for country in countries],
            any(urlsplit(a.get("href", "")).path == "/country/bih" for a in countries),
            [urljoin(url, a["href"]) for a in article.select(".rw-how-to-apply a[href]")])


def reliefweb_item(item):
    """The same fields from a feed item, whose description opens with "Countries:", "Organization:" and "Closing date:" lines."""
    description = BeautifulSoup(item.findtext("description") or "", "html.parser")

    def tagged(selector, label):
        node = description.select_one(selector)
        value = node.get_text(" ", strip=True) if node else ""
        return value[len(label):].strip() if value.startswith(label) else ""

    # A country name with a comma would count as two countries, which only asks for more residence evidence.
    countries = [name.strip() for name in tagged("div.tag.country", "Countries:").split(",") if name.strip()]
    employer = tagged("div.tag.source", "Organization:")
    closing = tagged("div.date.closing", "Closing date:")
    try:
        published = parsedate_to_datetime(item.findtext("pubDate") or "").date()
    except (TypeError, ValueError):
        published = None
    for node in description.select("div.tag, div.date"):
        node.decompose()
    how_to_apply = next((h for h in description.find_all(["h2", "h3"]) if "how to apply" in h.get_text().lower()), None)
    title = (item.findtext("title") or "").strip()
    if not all((title, employer, closing, countries)):
        raise ValueError("ReliefWeb job fields missing")
    return (title, employer, description.get_text(" ", strip=True), published, core.parse_date(closing),
            countries, "Bosnia and Herzegovina" in countries,
            [a["href"] for a in how_to_apply.find_all_next("a", href=True)] if how_to_apply else [])


def make_candidate(client, source, url, soup):
    """`soup` is the fetched job page, or the item of ReliefWeb's feed."""
    if soup is None:
        raise ValueError("Aggregator vacancy must be HTML")
    published = None
    application = ""
    eligibility = ""
    if source.adapter == "reliefweb":
        title, employer_name, text, published, deadline, locations, in_country, apply_links = reliefweb_item(soup) if reliefweb_feed(source) else reliefweb_page(url, soup)
        if not published or not deadline:
            raise ValueError("ReliefWeb dates invalid")
        location = "; ".join(locations)
        city = core.city_name(text) if len(locations) == 1 else ""
        if len(locations) > 1:
            # Multi-country tags alone do not prove that this role can be based in BiH.
            residence = re.search(r"(?:resid\w*|work|based|location)[^.!?]{0,250}Bosnia(?: and | & )Herzegovina", text, re.I)
            in_country = in_country and bool(residence)
            if in_country:
                location += ". " + residence.group(0)
                eligibility = "Regionalna pozicija: BiH je jedna od dozvoljenih zemalja boravka/rada. Provjerite uslove u oglasu."
        apply_links = list(dict.fromkeys(link for link in map(safe_url, apply_links) if link))
        if len(apply_links) == 1:
            application = apply_links[0]
        withdrawn = False
    else:
        heading = soup.select_one("#job-description h1")
        header = heading.parent if heading else None
        body = soup.select_one("#job-description")
        employer = header.select_one('[type="bodyEmphasis"]') if header else None
        locations = header.select('[type="body"]') if header else []
        if not all((heading, body, employer, locations)):
            raise ValueError("Impactpool job fields missing")
        location = locations[0].get_text(" ", strip=True)
        in_country = bool(core.LOCATION.search(location))
        city = core.city_name(location)
        header_text = header.get_text(" ", strip=True)
        deadline = core.parse_deadline(header_text)
        text = body.get_text(" ", strip=True)
        withdrawn = bool(re.search(r"(?:this (?:job|position|vacancy) (?:is|has been) (?:now )?closed|no longer accepting applications)", text, re.I))
        application = impactpool_application(client, url) if not withdrawn else ""
        # Impactpool does not expose a publication date in the inspected public
        # page. Do not substitute today's date or the age of a reused portal ID.
        stamp = header.select_one("time[itemprop=datePosted][datetime]")
        published = core.parse_date(stamp["datetime"][:10]) if stamp else None
        title, employer_name = heading.get_text(" ", strip=True), employer.get_text(" ", strip=True)
    title, employer_name = title[:400], employer_name[:240]
    excluded = bool(core.EXCLUDED.search(title) or re.search(r"\b(?:unpaid|neplaćen[aeo]?)\b", text, re.I))
    fresh = bool(deadline and deadline >= timezone.localdate())
    eligible = in_country and fresh and not excluded and not withdrawn
    year_proven = bool(published and published.year == core.TARGET_YEAR)
    in_scope = published.year == core.TARGET_YEAR if published else bool(deadline and deadline.year >= core.TARGET_YEAR)
    reasons = [reason for condition, reason in [(not in_country, "Mjesto rada u BiH nije potvrđeno"), (not deadline, "Rok nije naveden"), (bool(deadline) and not fresh, "Rok je istekao"), (excluded, "Isključena vrsta angažmana"), (withdrawn, "Oglas je zatvoren"), (not year_proven, "Godina objave nije potvrđena")] if condition]
    evidence = f"Employer: {employer_name}. Location: {location}. " + (f"Published {published.isoformat()}. " if published else "") + (f"Closing date {deadline.isoformat()}. " if deadline else "") + text
    candidate = core.Candidate(url, title, evidence[:100_000], city, deadline, published,
                               hashlib.sha256(evidence.encode()).hexdigest(), location, eligibility,
                               eligible, in_scope, year_proven, "; ".join(reasons), excluded,
                               core.opportunity_type(title), core.recruitment_scope(title, text), withdrawn)
    candidate.employer_name = employer_name
    candidate.application_url = application
    candidate.external_id = re.search(r"/jobs?/(\d+)", urlsplit(url).path)[1]
    return candidate
