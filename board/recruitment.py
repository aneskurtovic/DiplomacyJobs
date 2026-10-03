"""Official mission recruitment lists added after the October discovery audit.

Each adapter checks its listing structure before accepting an empty result. Global
portals filter employer and duty station separately from incidental body mentions.
"""
import ast
import gzip
import json
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from urllib.parse import parse_qsl, urljoin, urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from . import ingest as core

TURKISH_JOB = re.compile(r"mahalli\s+k[âa]tip|sözleşmeli\s+sekreter|personel\s+alımı|işe\s+alım|job\s+vacanc|local\s+staff", re.I)
SPANISH_MONTHS = dict(zip("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), range(1, 13)))


def text(node):
    return node.get_text(" ", strip=True).replace("\u200b", "").replace("\xa0", " ") if node else ""


def local_url(base, href, prefix=None):
    url = core.canonicalize(urljoin(base, href))
    path = urlsplit(url).path
    if urlsplit(url).hostname != urlsplit(base).hostname or (prefix and path != prefix.rstrip("/") and not path.startswith(prefix.rstrip("/") + "/")):
        raise ValueError("Recruitment link outside official source")
    return url


def put(evidence, url, title, body, published=None, deadline=None, closed=False):
    evidence[url] = (f"{title}. " + (f"Published {published.isoformat()}. " if published else "")
                     + (f"Closing date {deadline.isoformat()}. " if deadline else "")
                     + ("Unfortunately, this position has been closed. " if closed else "") + body)
    return url, title[:400]


def turkey_links(client, source, soup, evidence):
    # The English translation omits local recruitment notices. Select Turkish in
    # the same session, through the site's public language switch.
    switch = urljoin(source.url, "/Mission/ChangeLanguage?cultureCode=tr-TR&languageCode=50002")
    response = core.request(client, "get", switch)
    response.raise_for_status()
    _, soup = core.fetch(client, source.url)
    section = soup.select_one("#announcements") if soup else None
    if section is None or not re.search(r"Duyurular", text(soup.title), re.I):
        raise ValueError("Turkish local announcements/language missing")
    cards = section.select("a[href*='/Mission/ShowAnnouncement/']")
    if not cards:
        raise ValueError("Turkish announcement cards missing")
    if section.select("a[href*='page='], .pagination, [data-total]"):
        raise ValueError("Turkish announcements gained pagination; review adapter")
    result = []
    for card in cards:
        heading, publisher, stamp = (card.select_one(selector) for selector in (".ks-announcement-header", ".ks-announcement-from", ".ks-announcement-date"))
        published = core.parse_date(text(stamp))
        if not heading or not publisher or not published:
            raise ValueError("Turkish announcement fields changed")
        mission = source.adapter_config["mission_name"]
        if mission.casefold() not in text(publisher).casefold():
            raise ValueError("Non-local publisher in Turkish mission section")
        if published.year != core.TARGET_YEAR or not TURKISH_JOB.search(text(heading)):
            continue
        url = local_url(source.url, card["href"], "/Mission/ShowAnnouncement/")
        body, detail = core.fetch(client, url)
        content = detail.select_one("#mainAnnouncements") if detail else None
        if not content:
            raise ValueError("Turkish vacancy article missing")
        body = text(content)
        if not re.search(re.escape(mission) + r"|büyükelçiliğimiz|başkonsolosluğumuz", body, re.I):
            raise ValueError("Turkish recruitment employer unconfirmed in article")
        # A labelled application deadline is required; the publication date and
        # interview/exam dates are never substituted for a deadline.
        match = re.search(r"(?:son başvuru tarihi|başvurular[^.]{0,60}?en geç)\D{0,20}(\d{1,2}[./]\d{1,2}[./]\d{4})", body, re.I)
        deadline = core.parse_date(match.group(1)) if match else core.parse_deadline(body)
        result.append(put(evidence, url, text(heading), f"Location: {source.organization.city}. Employer: {text(publisher)}. {body}", published, deadline))
    return result


def spanish_date(value):
    match = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+(?:del?\s+)?(20\d{2})", value, re.I)
    if not match:
        return None
    try:
        return date(int(match[3]), SPANISH_MONTHS[match[2].lower()], int(match[1]))
    except (KeyError, ValueError):
        return None


def spain_links(client, source, soup, evidence):
    content = soup.select_one(".single__text")
    if not content or "OFERTAS ACTUALES" not in text(content).upper():
        raise ValueError("Spanish employment content missing")
    # Split dated updates into blocks. The same heading appears on results and
    # exam lists; only a call/bases PDF is an opportunity, not every attachment.
    blocks, current = [], None
    for node in content.find_all(["h2", "p", "ul", "div"], recursive=True):
        if node.name == "div" and node.find(["h2", "p", "ul", "div"]):
            continue
        value = text(node)
        if re.match(r"s\s*a\s*r\s*a\s*j\s*e\s*v\s*o\s*,", value, re.I) and len(value) < 100 and (stamp := spanish_date(value)):
            current = {"date": stamp, "parts": [], "links": [], "role": ""}
            blocks.append(current)
        elif current:
            current["parts"].append(value)
            role = re.search(r"CATEGOR[IÍ]A DE\s+([^\n.]+)", value, re.I)
            if role:
                current["role"] = role[1].strip().upper()
            current["links"] += [(text(a), a["href"]) for a in node.select("a[href]")]
    if not blocks:
        if re.search(r"no hay ofertas|no existen ofertas", text(content), re.I):
            return []
        raise ValueError("Spanish recruitment process dates missing")
    result, selected = [], set()
    for block in sorted(blocks, key=lambda item: item["date"], reverse=True):
        if block["date"].year != core.TARGET_YEAR:
            continue
        role = block["role"]
        if not role:
            raise ValueError("Spanish recruitment category missing")
        calls = [(label, href) for label, href in block["links"] if re.search(r"convocatoria|bases", label, re.I) and not re.search(r"resultado|lista|calificaci[oó]n|admitidos", label, re.I)]
        if not calls or role in selected:
            continue
        selected.add(role)
        final = any(other["role"] == role and other["date"] >= block["date"] and re.search(r"lista definitiva.*(?:resultado|calificaciones finales)|proceso.*(?:finalizado|cancelado)", " ".join(other["parts"]), re.I) for other in blocks)
        # Use the newest revised call and its PDF as the canonical advert.
        label, href = calls[-1]
        url = local_url(source.url, href, "/Embajadas/sarajevo/")
        if not urlsplit(url).path.lower().endswith(".pdf"):
            raise ValueError("Spanish call is no longer a PDF")
        body, _ = core.fetch(client, url)
        # PDF applications have an explicit full date; incomplete inline dates
        # can otherwise inherit a year from an unrelated historical process.
        normalized = re.sub(r"\s+", " ", body)
        match = re.search(r"(?:plazo de presentaci[oó]n de solicitudes|fecha de finalizaci[oó]n)[^.;]{0,150}?(\d{1,2}\s+de\s+\w+\s+(?:del?\s+)?20\d{2})", normalized, re.I)
        deadline = spanish_date(match[1]) if match else None
        if not deadline:
            inline = re.search(r"plazo de presentaci[oó]n de solicitudes[^.;]{0,200}?finaliza (?:el\s+)?(\d{1,2})\s+de\s+(\w+)", " ".join(block["parts"]), re.I)
            if inline:
                try:
                    deadline = date(block["date"].year, SPANISH_MONTHS[inline[2].lower()], int(inline[1]))
                except (KeyError, ValueError):
                    raise ValueError("Spanish revised application deadline invalid")
        result.append(put(evidence, url, f"{role.title()} — Ambasada Španije", normalized, block["date"], deadline, final))
    return result


def brazil_links(client, source, soup, evidence):
    content = soup.select_one("#content")
    if not content or not re.search(r"PROCESSO SELETIVO|OGLAS ZA POSAO", text(content), re.I):
        raise ValueError("Brazil selection folder missing")
    if content.select(".pagination, a[href*='b_start']"):
        raise ValueError("Brazil folder gained pagination")
    result = []
    for link in content.select("a[href]"):
        if not re.search(r"processo seletivo|oglas za posao", text(link), re.I):
            continue
        process = local_url(source.url, link["href"], urlsplit(source.url).path + "/")
        closed = bool(re.search(r"encerrado|zatvoreno|cancelado", text(link), re.I))
        _, detail = core.fetch(client, process)
        language = detail.select_one("#content a[href*='bhs']") if detail else None
        if not language:
            raise ValueError("Brazil BHS process page missing")
        _, notice = core.fetch(client, local_url(source.url, language["href"]))
        article = notice.select_one("#content-core") if notice else None
        if not article:
            raise ValueError("Brazil vacancy content missing")
        advert = next((a for a in article.select("a[href]") if re.search(r"kompletnu obavijest|edital|oglas", text(a), re.I) and urlsplit(a["href"]).path.lower().endswith(".pdf")), None)
        if not advert:
            raise ValueError("Brazil vacancy PDF missing")
        url = local_url(source.url, advert["href"])
        body, _ = core.fetch(client, url)
        if len(body.strip()) < 150 and not closed:
            # A scanned advert has no text to read dates from; the CMS page dates are reused from 2023.
            # It becomes a review lead with the process year the embassy names; a reviewer reads the PDF.
            year = re.search(r"\b(20\d{2})\b", text(link))
            if not year:
                raise ValueError("Brazil scanned vacancy PDF has no process year")
            result.append(put(evidence, url, "Oglas za posao — Ambasada Brazila", f"Location: Sarajevo. Recruitment year: {year[1]}. Skenirani PDF bez čitljivog teksta; rok i uslove pročitati u PDF-u. {text(article)}"))
            continue
        # Never use the CMS's 2023 creation date as the 2026 call date.
        published = core.parse_published(body)
        if not published:
            stamp = re.search(r"Sarajevo,?\s+(" + core.DATE_TEXT + r")", body, re.I)
            published = core.parse_date(stamp[1]) if stamp else None
        result.append(put(evidence, url, "Oglas za posao — Ambasada Brazila", body, published, core.parse_deadline(body), closed))
    if not result:
        raise ValueError("Brazil selection links missing")
    return result


def slovenia_links(client, source, soup, evidence):
    result, seen_pages, seen_jobs = [], set(), set()
    page, page_url = soup, source.adapter_config.get("listing_url", source.url)
    for _ in range(core.MAX_LISTING_PAGES):
        table = page.select_one("table.employment-list-table") if page else None
        if table is None:
            raise ValueError("Slovenian employment table missing")
        rows = table.select("tr:has(td.td-title)")
        signature = tuple(text(row.select_one(".td-title")) for row in rows)
        if signature in seen_pages and rows:
            raise ValueError("Slovenian pagination repeats jobs")
        seen_pages.add(signature)
        for row in rows:
            link = row.select_one(".td-title a[href]")
            employer = text(row.select_one(".td-organisation"))
            published = core.parse_date(text(row.select_one(".td-publish-date")))
            deadline = core.parse_date(text(row.select_one(".td-due-date")))
            if not link or not employer or not published or not deadline:
                raise ValueError("Slovenian employment fields missing")
            url = local_url(source.url, link["href"], "/zbirke/delovna-mesta/")
            if url in seen_jobs:
                raise ValueError("Slovenian pages contain duplicate jobs")
            seen_jobs.add(url)
            title = text(link)
            # Central lists include secondments to unrelated international bodies.
            # Keep only employment at Slovenia's embassy, not election observers.
            if not re.search(r"Ministrstvo za zunanje", employer, re.I) or not re.search(r"veleposlaništv\w*.*(?:sarajev|bosn)|(?:sarajev|bosn).*veleposlaništv", title, re.I) or published.year != core.TARGET_YEAR:
                continue
            body, detail = core.fetch(client, url)
            article = detail.select_one("main") if detail else None
            if not article:
                raise ValueError("Slovenian vacancy article missing")
            body = text(article)
            station = re.search(r"(?:kraj (?:opravljanja dela|dela)|delovno mesto.*?v veleposlaništvu)[^.;]{0,100}(?:sarajev\w*|bosn\w*)", body, re.I)
            # Title proves mission; detail must independently identify duty station.
            if not station:
                raise ValueError("Slovenian embassy duty station unconfirmed")
            result.append(put(evidence, url, title, f"Location: Sarajevo. Employer: {employer}. {body}", published, deadline, "Zaključeno" in text(row)))
        next_link = next((a for a in page.select("a[href]") if text(a) == "Naprej"), None)
        if not next_link:
            if not rows and not re.search(r"ni zadetkov|ni rezultatov|ni (?:prostih )?delovnih mest|ni najdenih", text(page), re.I):
                raise ValueError("Slovenian empty listing lacks confirmation")
            return result
        next_url = local_url(source.url, next_link["href"], "/zbirke/delovna-mesta/")
        if dict(parse_qsl(urlsplit(next_url).query)).get("status") != "ongoing" or dict(parse_qsl(urlsplit(next_url).query)).get("org[0]") != "3745" or next_url == core.canonicalize(page_url):
            raise ValueError("Slovenian pagination lost active/employer filter")
        _, page = core.fetch(client, next_url)
        page_url = next_url
    raise ValueError("Slovenian listing exceeds page limit")


def public_script(client, url):
    response = core.request(client, "get", url)
    response.raise_for_status()
    if response.status_code != 200 or len(response.content) > 5_000_000 or urlsplit(str(response.url)).hostname != urlsplit(url).hostname or "javascript" not in response.headers.get("content-type", ""):
        raise ValueError("Canadian public data script unusable")
    return response.text


def canadian_arrays(script):
    arrays = []
    # Parse only string literals containing JSON; never execute scraped JavaScript.
    for match in re.finditer(r"JSON\.parse\(('(?:\\.|[^'\\])*')\)", script):
        value = json.loads(ast.literal_eval(match[1]))
        if isinstance(value, list):
            arrays.append(value)
    return arrays


def canada_links(client, source, soup, evidence):
    # Gatsby embeds the entire job inventory in a published build chunk. Resolve
    # its hash on every scan; no stale hardcoded bundle name or browser is needed.
    response = core.request(client, "get", source.url)
    response.raise_for_status()
    if response.status_code != 200 or len(response.content) > 5_000_000:
        raise ValueError("Canadian recruitment homepage unusable")
    landing = BeautifulSoup(response.text, "html.parser")
    runtime = landing.select_one("script[src*='webpack-runtime-']")
    if not runtime:
        raise ValueError("Canadian build manifest missing")
    script = public_script(client, local_url(source.url, runtime["src"]))
    maps = re.search(r"\.u=function\(\w+\).*?return\((\{[^}]+\}).*?\+\"-\"\+(\{[^}]+\})", script)
    if not maps:
        raise ValueError("Canadian build chunk map changed")
    names, hashes = [dict(re.findall(r'(\d+):"([^"\\]+)"', part)) for part in maps.groups()]
    if len([name for name in names.values() if re.fullmatch(r"[a-f0-9]{40}", name)]) > core.MAX_LISTING_PAGES:
        raise ValueError("Canadian build exceeds data chunk limit")
    jobs, missions = None, None
    for chunk, name in names.items():
        if not re.fullmatch(r"[a-f0-9]{40}", name) or chunk not in hashes:
            continue
        bundle = public_script(client, local_url(source.url, f"/{name}-{hashes[chunk]}.js"))
        for array in canadian_arrays(bundle):
            if array and isinstance(array[0], dict) and "applyUrl" in array[0] and "jobCode" in array[0]:
                jobs = array
            if array and isinstance(array[0], dict) and "SYMBOL" in array[0] and "country" in array[0]:
                missions = array
        if jobs is not None and missions is not None:
            break
    if jobs is None or missions is None:
        raise ValueError("Canadian complete job/mission arrays missing")
    mission_map = {item["SYMBOL"]: item for item in missions}
    result, seen = [], set()
    def field(job, key):
        values = job.get(key)
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
            raise ValueError(f"Canadian job field changed: {key}")
        return values[0].strip()
    for job in jobs:
        code, station = field(job, "jobCode"), field(job, "Location")
        if code in seen:
            raise ValueError("Duplicate Canadian job code")
        seen.add(code)
        if not code.endswith("-en"):
            continue
        symbol = field(job, "mission")
        if not core.LOCATION.search(station):
            continue
        mission = mission_map.get(symbol)
        if not mission:
            raise ValueError("Canadian recruitment mission code unknown")
        if not core.LOCATION.search(mission["country"] + " " + mission["city"]):
            continue
        if not re.search(r"canada", station, re.I):
            raise ValueError("Canadian BiH employer/duty station unconfirmed")
        # This organization is an honorary consulate. An embassy job cannot be
        # attributed to it merely because it serves Bosnia from another country.
        if not re.search(r"honorary consulate", station, re.I):
            raise ValueError("Canadian BiH role does not belong to Sarajevo honorary consulate")
        application = field(job, "applyUrl")
        parts = urlsplit(application)
        if parts.scheme != "https" or not core.trusted_host(parts.hostname or "", "hiringplatform.ca"):
            raise ValueError("Canadian application host changed")
        title = field(job, "title")
        try:
            published = parsedate_to_datetime(field(job, "listDate")).date()
            deadline = date(int(field(job, "CloseDateYear")), core.MONTHS[field(job, "CloseDateMonth").split(" / ")[0].lower()], int(field(job, "CloseDateDay")))
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Canadian recruitment dates invalid") from exc
        body = BeautifulSoup(field(job, "description"), "html.parser").get_text(" ", strip=True)
        url = core.canonicalize(application)
        result.append(put(evidence, url, title, f"Location: {station}. Locally engaged staff. Salary: {field(job, 'Salary')}. {field(job, 'TermDetails')}. {body}", published, deadline))
    return result


ATOM = "{http://www.w3.org/2005/Atom}"
FEED_HISTORY = "{http://purl.org/syndication/history/1.0}"
PS_DEADLINE = re.compile(r"Deadline:\s*(?:[A-Za-z]+day,?\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})")


def xml_document(client, url):
    response = core.request(client, "get", url)
    response.raise_for_status()
    content = response.content
    # Sitemaps are often served as .xml.gz files, not with a gzip transfer encoding.
    if content[:2] == b"\x1f\x8b":
        content = gzip.GzipFile(fileobj=BytesIO(content)).read(5_000_001)
    if response.status_code != 200 or len(content) > 5_000_000 or urlsplit(str(response.url)).hostname != urlsplit(url).hostname:
        raise ValueError(f"Unusable XML document: {url}")
    return ElementTree.fromstring(content)


def peoplesoft_links(client, source, soup, evidence):
    """PeopleSoft HCM job-posting Atom feed (EIB Group). The feed declares itself
    complete; an entry is kept when its title or "based in/at" sentence names a BiH
    place. Entries without a stated deadline are open until filled."""
    feed = xml_document(client, source.url)
    if feed.tag != ATOM + "feed" or feed.find(FEED_HISTORY + "complete") is None:
        raise ValueError("PeopleSoft feed is not a complete Atom feed")
    host, result, seen = urlsplit(source.url).hostname, [], set()
    for entry in feed.findall(ATOM + "entry"):
        title, link = (entry.findtext(ATOM + "title") or "").strip(), entry.find(ATOM + "link[@rel='alternate']")
        published = core.parse_date((entry.findtext(ATOM + "published") or "")[:10])
        if not title or link is None or not published:
            raise ValueError("PeopleSoft feed entry changed shape")
        url = core.canonicalize(link.get("href", ""))
        if urlsplit(url).hostname != host:
            raise ValueError("PeopleSoft job link outside the feed host")
        if url in seen:
            continue  # The same posting can appear twice in one feed.
        seen.add(url)
        body = BeautifulSoup(entry.findtext(ATOM + "content") or "", "html.parser").get_text(" ", strip=True)
        if not core.LOCATION.search(title) and not any(core.LOCATION.search(match[0]) for match in re.finditer(r"\bbased (?:in|at)\b[^.]{0,80}", body, re.I)):
            continue
        entity = re.search(r"\(Entity:\s*([^-)]+)", title)
        stated = PS_DEADLINE.search(body)
        deadline = core.parse_date(" ".join(stated.groups())) if stated else None
        clean = re.sub(r"\s*\(Entity:[^)]*\)\s*$", "", title)
        result.append(put(evidence, url, clean, f"Employer: {entity[1].strip() if entity else source.organization.name}. {body}", published, deadline))
    return result


def sitemap_links(client, source, soup, evidence):
    """Mission site without a vacancy list whose adverts are stand-alone articles
    (German embassy). Its daily-generated sitemap names every page, so articles
    newer than adapter_config.min_article_id are read, and those whose heading
    matches adapter_config.title_pattern are kept."""
    config = source.adapter_config or {}
    floor, prefix, pattern = int(config["min_article_id"]), config["path_prefix"], re.compile(config["title_pattern"], re.I)
    host = urlsplit(source.url).hostname
    index = xml_document(client, source.url)
    namespace = index.tag.split("}")[0] + "}" if index.tag.startswith("{") else ""
    maps = [loc.text.strip() for loc in index.iter(namespace + "loc")] if index.tag.endswith("sitemapindex") else []
    pages = []
    for document in [xml_document(client, url) for url in maps] if maps else [index]:
        pages += [loc.text.strip() for loc in document.iter(namespace + "loc")]
    if any(urlsplit(url).hostname != host for url in maps + pages) or not any(urlsplit(url).path.startswith(prefix) for url in pages):
        raise ValueError("Sitemap lists no pages of this mission")
    articles = [url for url in pages if (match := re.fullmatch(re.escape(prefix) + r"(\d+)-\1", urlsplit(url).path)) and int(match[1]) > floor]
    if len(articles) > core.MAX_DETAIL_LINKS:
        raise ValueError(f"{len(articles)} new sitemap articles; raise adapter_config.min_article_id")
    result = []
    for url in articles:
        body, page = core.fetch(client, url)
        heading = page.select_one("main h1.heading__title") if page else None
        stamp = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(?:Članak|Artikel|Article)", body)
        if not heading or not stamp:
            raise ValueError("Mission article heading or date missing")
        if not pattern.search(text(heading)):
            continue
        content = body[stamp.end():]
        # Headings are often just "Oglas za posao"; the employer label makes the board title useful.
        title = f"{text(heading)} — {config['employer_label']}" if config.get("employer_label") else text(heading)
        result.append(put(evidence, core.canonicalize(url), title, f"Location: {source.organization.city}. Employer: {source.organization.name}. {content}", core.parse_date(stamp[1]), core.parse_deadline(content)))
    return result


def wordpress_links(client, source, soup, evidence):
    """WordPress site's REST API: every post of the year in adapter_config.categories,
    minus exclude_categories. A post is kept when it carries all require_categories
    and its title matches the optional title_pattern. Used for a third-party board
    filtered to one employer (mreza-mira.net for GIZ; expired posts move to its
    archive category) and for an employer's own site (RYCO, whose Sarajevo office
    category is the location evidence, given as adapter_config.location)."""
    config = source.adapter_config or {}
    parts = urlsplit(source.url)
    if parts.scheme != "https" or not parts.path.rstrip("/").endswith("/wp-json/wp/v2/posts") or parts.query:
        raise ValueError("WordPress posts endpoint missing from source URL")
    query = {"categories": ",".join(str(int(value)) for value in config["categories"]), "after": f"{core.TARGET_YEAR}-01-01T00:00:00",
             "per_page": 100, "_fields": "id,date,link,title,content,categories"}
    if config.get("exclude_categories"):
        query["categories_exclude"] = ",".join(str(int(value)) for value in config["exclude_categories"])
    posts, page, pages, total = [], 1, 1, 0
    while page <= pages:
        if page > core.MAX_LISTING_PAGES:
            raise ValueError("WordPress job categories exceed the page limit")
        response = core.request(client, "get", source.url, params={**query, "page": page})
        response.raise_for_status()
        if "json" not in response.headers.get("content-type", "") or urlsplit(str(response.url)).hostname != parts.hostname or len(response.content) > 5_000_000:
            raise ValueError("WordPress API response unusable")
        batch = response.json()
        try:
            pages, total = int(response.headers["x-wp-totalpages"]), int(response.headers["x-wp-total"])
        except (KeyError, ValueError) as exc:
            raise ValueError("WordPress API paging headers missing") from exc
        if not isinstance(batch, list):
            raise ValueError("WordPress API response changed shape")
        posts += batch
        page += 1
    if len(posts) != total:
        raise ValueError(f"WordPress API listed {len(posts)} of {total} posts")
    pattern, required, result = re.compile(config.get("title_pattern", ""), re.I), {int(value) for value in config.get("require_categories", [])}, []
    for post in posts:
        title = BeautifulSoup(post["title"]["rendered"], "html.parser").get_text(" ", strip=True)
        if not pattern.search(title) or not required <= set(post.get("categories") or []):
            continue
        url = core.canonicalize(post["link"])
        if urlsplit(url).hostname != parts.hostname:
            raise ValueError("WordPress post link outside the board")
        body = BeautifulSoup(post["content"]["rendered"], "html.parser").get_text(" ", strip=True)
        context = (f"Location: {config['location']}. " if config.get("location") else "") + f"Employer: {source.organization.name}. " + (f"Advertised on {config['portal_name']}. " if config.get("portal_name") else "")
        result.append(put(evidence, url, title, context + body, core.parse_date(post["date"][:10]), core.parse_deadline(body)))
    return result


def notice_date(value):
    try:
        return datetime.strptime(value.split()[0], "%d-%b-%y").date()
    except (ValueError, IndexError):
        return None


def undpnotices_links(client, source, soup, evidence):
    """UNDP procurement notices (individual-consultant notices are published here, not on
    UNDP's job portal). The site's search by reference prefix (adapter_config.ref_prefix,
    e.g. UNDP-BIH) lists the country office's notices of the year; open rows whose process
    is IC - Individual contractor are kept, and each notice page adds country and duration.
    Its robots.txt disallows crawlers; the owner approved one daily search (2026-10-03)."""
    config = source.adapter_config or {}
    prefix = config["ref_prefix"]
    response = core.request(client, "post", source.url, data={"cur_notice_id": prefix})
    response.raise_for_status()
    if urlsplit(str(response.url)).hostname != urlsplit(source.url).hostname or len(response.content) > 5_000_000:
        raise ValueError("UNDP notice search response unusable")
    page = BeautifulSoup(response.text, "html.parser")
    rows = page.select("a.vacanciesTable__row")
    if not page.select_one(".vacanciesTable__header") or not rows:
        raise ValueError("UNDP notice search table missing or empty")
    today, result = core.timezone.localdate(), []
    for row in rows:
        cells = {text(cell.select_one(".vacanciesTable__cell__label")): text(cell.select_one("span")) for cell in row.select(".vacanciesTable__cell") if cell.select_one(".vacanciesTable__cell__label") and cell.select_one("span")}
        if not cells.get("Ref No", "").startswith(prefix):
            raise ValueError("UNDP notice search returned another office")
        published, deadline = notice_date(cells.get("Posted", "")), notice_date(cells.get("Deadline", ""))
        if not published or not deadline:
            raise ValueError("UNDP notice dates changed format")
        if not cells.get("Process", "").startswith("IC") or deadline < today:
            continue
        url = local_url(source.url, row["href"])
        body, detail = core.fetch(client, url)
        if detail is None or cells["Ref No"] not in body:
            raise ValueError("UNDP notice page changed")
        start = body.find("Introduction")
        result.append(put(evidence, url, cells["Title"], f"Location: {cells.get('UNDP Office/Country', '')}. Reference: {cells['Ref No']}. Individual contractor (consultancy). {body[start:] if start >= 0 else body}", published, deadline))
    return result


def kemlu_links(client, source, soup, evidence):
    """Indonesian MFA portal (kemlu.go.id) public content API. The portal is a JavaScript
    application; its /contentMenu call returns a section's publications with a count
    (meta.filtered), which every scan must reach. adapter_config.sections maps a menu slug
    to a title pattern: an empty pattern keeps every post (the embassy's Career section),
    otherwise only matching titles are kept (career posts in News)."""
    config = source.adapter_config or {}
    portal, host = config["portal"], urlsplit(source.url).hostname
    result = []
    for section, title_pattern in config["sections"].items():
        posts, filtered = [], None
        for page in range(1, core.MAX_LISTING_PAGES + 1):
            params = [("slug[]", portal), ("slug[]", section), ("type", "menu"), ("portal", portal), ("page", page), ("limit", 100),
                      ("tag", ""), ("order_dir", "desc"), ("order_by", "publish_date"), ("lang", "en")]
            response = core.request(client, "get", source.url, params=params)
            response.raise_for_status()
            if urlsplit(str(response.url)).hostname != host or "json" not in response.headers.get("content-type", "") or len(response.content) > 5_000_000:
                raise ValueError("Kemlu content API response unusable")
            data = response.json().get("data") or {}
            meta, batch = data.get("meta") or {}, data.get("publication")
            if not isinstance(batch, list) or "filtered" not in meta:
                raise ValueError(f"Kemlu section {section} changed shape")
            filtered = int(meta["filtered"])
            posts += batch
            if not batch or len(posts) >= filtered:
                break
        if len(posts) != filtered:
            raise ValueError(f"Kemlu section {section} listed {len(posts)} of {filtered} posts")
        pattern = re.compile(title_pattern, re.I) if title_pattern else None
        for post in posts:
            title = (post.get("title_eng") or post.get("title") or "").strip()
            if pattern and not pattern.search(f"{post.get('title', '')} {title}"):
                continue
            published = core.parse_date((post.get("publish_date") or "")[:10])
            url = core.canonicalize(f"https://kemlu.go.id/{portal}/{section}/{post['slug']}")
            body = BeautifulSoup(" ".join(post.get(key) or "" for key in ("content_detail_eng", "content_detail")), "html.parser").get_text(" ", strip=True)
            result.append(put(evidence, url, title, f"Location: Sarajevo. Employer: {source.organization.name}. {body}", published, core.parse_deadline(body)))
    return result


ADAPTERS = {"kemlu": kemlu_links, "undpnotices": undpnotices_links, "wordpress": wordpress_links, "turkey": turkey_links, "spain": spain_links, "brazil": brazil_links, "slovenia": slovenia_links, "canadales": canada_links, "peoplesoft": peoplesoft_links, "sitemap": sitemap_links}
