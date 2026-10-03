"""Conservative cross-source identity, without merging source-owned histories."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from .text import fold

AGGREGATORS = {"reliefweb", "impactpool"}
# Explicit employer aliases; a short acronym found in an arbitrary name is not proof.
EMPLOYERS = {
    "unicef": ["UNICEF u Bosni i Hercegovini", "UNICEF - United Nations Children’s Fund"],
    "undp": ["UNDP u Bosni i Hercegovini", "UNDP - United Nations Development Programme"],
    "unfpa": ["UNFPA u Bosni i Hercegovini", "UNFPA - United Nations Population Fund"],
    "unwomen": ["UN Women u Bosni i Hercegovini", "UN WOMEN - United Nations Entity for Gender Equality and the Empowerment of Women"],
    "osce": ["Misija OSCE-a u Bosni i Hercegovini", "OSCE - Organization for Security and Co-operation in Europe"],
}


def normalized(value):
    return " ".join(re.findall(r"\w+", fold(value)))


ALIASES = {normalized(name): key for key, names in EMPLOYERS.items() for name in [key, *names]}


def employer_key(name):
    key = normalized(name)
    return ALIASES.get(key, key)


def url_key(url):
    """Drop tracking only; retain requisition parameters and multi-tenant portal paths."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    host = parts.hostname.lower().removeprefix("www.")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    path = parts.path.rstrip("/")
    # UNICEF publishes the same requisition under multiple locale/channel paths.
    if host == "jobs.unicef.org" and (match := re.search(r"/job/(\d+)(?:/|$)", path)):
        return f"{host}/job/{match[1]}"
    # Oracle Candidate Experience: aggregators link /requisitions/job/N or /preview/N, in any locale, for the site's /job/N.
    if host.endswith(".oraclecloud.com") and (match := re.search(r"/CandidateExperience/[^/]+/sites/([^/]+)/(?:requisitions/)?(?:job|preview)/(\d+)(?:/|$)", path, re.I)):
        return f"{host}/sites/{match[1]}/job/{match[2]}"
    if path.lower() in {"", "/jobs", "/careers", "/vacancies", "/search", "/en/jobs", "/en/careers"} and not query:
        return ""  # Shared careers homepages never identify one vacancy.
    return host + path + ("?" + urlencode(sorted(query)) if query else "")


def same_vacancy(left, right):
    if left.source_id == right.source_id:
        return False
    if left.source_published_at and right.source_published_at and abs((left.source_published_at - right.source_published_at).days) > 45:
        return False  # Repeated recruitment rounds need separate records.
    left_urls = {key for url in (left.canonical_url, left.application_url) if (key := url_key(url))}
    right_urls = {key for url in (right.canonical_url, right.application_url) if (key := url_key(url))}
    if left_urls & right_urls:
        return True
    # Never merge on a similar title alone, nor across different employers or deadlines.
    return bool(left.deadline and left.deadline == right.deadline and left.city and right.city
                and normalized(left.city) == normalized(right.city)
                and employer_key(left.employer_name) == employer_key(right.employer_name)
                and normalized(left.title) == normalized(right.title))


def unique_visible_ids(query):
    """Choose one current public record; keep every source's evidence in the database.

    A known official record in review/closed also suppresses its syndicated copy:
    aggregation must not undo an employer withdrawal or a human review decision.
    Recomputed on read so disabling, closing, editing or expiring jobs takes effect
    immediately, regardless of scrape order.
    """
    from .models import Job
    rows = list(query.select_related("source__organization").defer("raw_text"))
    blockers = []
    if any(job.source.adapter in AGGREGATORS for job in rows):
        blockers = list(Job.objects.exclude(source__adapter__in=AGGREGATORS)
                        .exclude(pk__in=[job.pk for job in rows])
                        .select_related("source__organization").defer("raw_text"))
    rows.sort(key=lambda job: (job.source.adapter in AGGREGATORS, job.first_seen_at, job.pk))
    winners = []
    for job in rows:
        if job.source.adapter in AGGREGATORS and any(same_vacancy(job, other) for other in blockers):
            continue
        if not any(same_vacancy(job, other) for other in winners):
            winners.append(job)
    return [job.pk for job in winners]
