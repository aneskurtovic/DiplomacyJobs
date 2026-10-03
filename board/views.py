from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from django.core.paginator import InvalidPage, Paginator
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.conf import settings
from django.utils import timezone
from .models import Job, Organization, Source
from .text import fold
from .dedup import employer_key, unique_visible_ids

STALE_AFTER = timedelta(hours=48)
DISCOVERY_RECHECK_AFTER = timedelta(days=90)


def visible_jobs():
    """Published, current jobs: what the public board and the feed show."""
    today = timezone.localdate()
    cutoff = timezone.now() - timedelta(days=30)
    query = Job.objects.filter(status="published", source__enabled=True).filter(Q(deadline__gte=today) | Q(deadline__isnull=True)).filter(Q(deadline__isnull=False) | Q(first_seen_at__gte=cutoff) | Q(last_reviewed_at__gte=cutoff))
    return query.filter(pk__in=unique_visible_ids(query))


def filter_jobs(query, params):
    search = params.get("q", "").strip()[:100]
    employer = params.get("employer", "")
    city = params.get("city", "")
    kind = params.get("type", "")
    scope = params.get("scope", "")
    if search:
        # Neither database ignores diacritics in a portable way; visible jobs are few, so matching is done on folded text.
        needle = fold(search)
        rows = query.select_related("source__organization").defer("raw_text")
        query = query.filter(pk__in=[job.pk for job in rows if needle in fold(" ".join((job.title, job.city, job.employer_name)))])
    if employer.isdecimal() and len(employer) <= 18:
        organization = Organization.objects.filter(pk=int(employer)).first()
        key = employer_key(organization.name) if organization else None
        query = query.filter(pk__in=[job.pk for job in query.select_related("source__organization") if employer_key(job.employer_name) == key])
    elif employer.startswith("name:"):
        query = query.filter(pk__in=[job.pk for job in query.select_related("source__organization") if employer_key(job.employer_name) == employer_key(employer[5:])])
    if city:
        query = query.filter(city=city[:100])
    if kind in dict(Job.TYPE):
        query = query.filter(opportunity_type=kind)
    if scope in ("national", "international"):
        query = query.filter(scope=scope)
    return query, {"search": search, "employer": employer, "city": city, "kind": kind, "scope": scope}


def jobs(request):
    today = timezone.localdate()
    visible = visible_jobs()
    query, filters = filter_jobs(visible, request.GET)
    sort = "deadline" if request.GET.get("sort") == "deadline" else ""
    order = (F("deadline").asc(nulls_last=True), "-first_seen_at", "-pk") if sort else ("-first_seen_at", "-pk")
    # A page past the end or a non-number is not found, rather than a silent copy of another page under a new URL.
    try:
        page = Paginator(query.select_related("source__organization").order_by(*order), 20).page(request.GET.get("page") or 1)
    except InvalidPage:
        raise Http404("Nema te stranice")
    for job in page:
        job.days_left = (job.deadline - today).days if job.deadline else None
        job.is_new = job.first_seen_at >= timezone.now() - timedelta(days=3)
    # The feed takes the same filters, so the current search can be followed.
    feed_query = urlencode({key: filters[name] for key, name in (("q", "search"), ("employer", "employer"), ("city", "city"), ("type", "kind"), ("scope", "scope")) if filters[name]})
    # Page links keep only the active filters and sort.
    page_query = "&".join(part for part in (feed_query, urlencode({"sort": sort}) if sort else "") if part)
    known = {employer_key(org.name): org for org in Organization.objects.all()}
    employers = {}
    for job in visible.select_related("source__organization").defer("raw_text"):
        key = employer_key(job.employer_name)
        employers[key] = known.get(key) or {"pk": "name:" + job.employer_name, "name": job.employer_name}
    return render(request, "board/jobs.html", {"page": page, **filters, "sort": sort, "feed_query": feed_query, "page_query": page_query, "employers": sorted(employers.values(), key=lambda item: item["name"] if isinstance(item, dict) else item.name), "cities": visible.exclude(city="").values_list("city", flat=True).distinct().order_by("city"), "types": [(value, label) for value, label in Job.TYPE if visible.filter(opportunity_type=value).exists()]})


def sources(request):
    organizations = Organization.objects.prefetch_related("sources").order_by("name")
    today = timezone.localdate()
    # Undated leads stay in the review queue until expire_jobs closes them as stale after 60 days.
    cutoff = timezone.now() - timedelta(days=60)
    published = visible_jobs()
    counts = dict(published.values("source_id").annotate(total=Count("id")).values_list("source_id", "total"))
    review_counts = dict(Job.objects.filter(status="review", source__enabled=True).filter(Q(deadline__gte=today) | Q(deadline__isnull=True, first_seen_at__gte=cutoff)).values("source_id").annotate(total=Count("id")).values_list("source_id", "total"))
    rows = []
    totals = {"available": 0, "empty": 0, "review": 0, "partial": 0, "unavailable": 0, "pending": 0, "not_found": 0, "integration": 0}
    for organization in organizations:
        organization_sources = list(organization.sources.all())
        active_urls = {source.url for source in organization_sources if source.enabled and source.adapter != "none"}
        audit_current = bool(organization.recruitment_checked_at and today - DISCOVERY_RECHECK_AFTER <= organization.recruitment_checked_at <= today and organization.recruitment_evidence_url and organization.recruitment_notes)
        for source in organization_sources or [None]:
            # Keep history, but do not count an explicitly replaced disabled endpoint twice.
            if source and not source.enabled and (source.adapter_config or {}).get("superseded_by") in active_urls:
                continue
            last_check_failed = bool(source and source.last_attempt_at and (not source.last_success_at or source.last_attempt_at > source.last_success_at))
            # If the daily run stops, old counts must not keep reading as a healthy source.
            stale = bool(source and source.enabled and source.last_success_at and source.last_success_at < timezone.now() - STALE_AFTER)
            if source and (source.status in ("blocked", "failing") or last_check_failed or stale):
                status = "unavailable"
            elif source and source.enabled and source.status == "verified" and source.last_success_at:
                status = "partial" if (source.adapter_config or {}).get("partial_listing") else "available" if counts.get(source.pk, 0) else "review" if review_counts.get(source.pk, 0) else "empty"
            elif audit_current and organization.recruitment_status in ("not_found", "integration", "blocked"):
                status = "unavailable" if organization.recruitment_status == "blocked" else organization.recruitment_status
            else:
                status = "pending"
            totals[status] += 1
            url = source.url if source else organization.website or organization.recruitment_evidence_url
            rows.append({"organization": organization, "source": source, "status": status, "count": counts.get(source.pk, 0) if source else 0, "review_count": review_counts.get(source.pk, 0) if source else 0, "url": url, "domain": urlsplit(url).hostname if url else "", "audit_current": audit_current})
    selected = request.GET.get("status", "all")
    if selected not in (*totals, "all"):
        selected = "all"
    visible_rows = rows if selected == "all" else [row for row in rows if row["status"] == selected]
    latest = Source.objects.filter(last_success_at__isnull=False).order_by("-last_success_at").values_list("last_success_at", flat=True).first()
    return render(request, "board/sources.html", {"rows": visible_rows, "total": len(rows), "organizations_total": organizations.count(), "shown": len(visible_rows), "totals": totals, "selected": selected, "open_jobs": published.count(), "latest": latest})


def absolute(request, path):
    return f"{settings.PUBLIC_BASE_URL}{path}" if settings.PUBLIC_BASE_URL else request.build_absolute_uri(path)


def public_base(request):
    """Template origin for canonical and Open Graph URLs."""
    return {"public_base": settings.PUBLIC_BASE_URL or f"{request.scheme}://{request.get_host()}"}


def robots(request):
    lines = ["User-agent: *", "Disallow: /admin/", "Disallow: /health/", f"Sitemap: {absolute(request, '/sitemap.xml')}"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def sitemap(request):
    urls = "".join(f"<url><loc>{absolute(request, path)}</loc><changefreq>daily</changefreq></url>" for path in ("/", "/sources/"))
    return HttpResponse(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', content_type="application/xml")


def health(request):
    return HttpResponse("ok", content_type="text/plain")


def scrape_health(request):
    """For external monitoring. /health/ stays a liveness check because the scheduler container waits on it."""
    stale = Source.objects.filter(enabled=True).exclude(adapter="none").filter(Q(last_success_at__isnull=True) | Q(last_success_at__lt=timezone.now() - STALE_AFTER))
    names = list(stale.values_list("url", flat=True)[:20])
    return HttpResponse("ok" if not names else "stale:\n" + "\n".join(names), content_type="text/plain", status=200 if not names else 503)
