from datetime import timedelta
from urllib.parse import urlsplit
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from .models import Job, Organization, Source

STALE_AFTER = timedelta(hours=48)


def visible_jobs():
    """Published, current jobs: what the public board and the feed show."""
    today = timezone.localdate()
    cutoff = timezone.now() - timedelta(days=30)
    return Job.objects.filter(status="published", source__enabled=True).filter(Q(deadline__gte=today) | Q(deadline__isnull=True)).filter(Q(deadline__isnull=False) | Q(first_seen_at__gte=cutoff) | Q(last_reviewed_at__gte=cutoff))


def filter_jobs(query, params):
    search = params.get("q", "").strip()[:100]
    employer = params.get("employer", "")
    city = params.get("city", "")
    kind = params.get("type", "")
    if search:
        query = query.filter(Q(title__icontains=search) | Q(source__organization__name__icontains=search) | Q(city__icontains=search))
    if employer.isdecimal() and len(employer) <= 18:
        query = query.filter(source__organization_id=int(employer))
    if city:
        query = query.filter(city=city[:100])
    if kind in dict(Job.TYPE):
        query = query.filter(opportunity_type=kind)
    return query, {"search": search, "employer": employer, "city": city, "kind": kind}


def jobs(request):
    today = timezone.localdate()
    visible = visible_jobs()
    query, filters = filter_jobs(visible, request.GET)
    sort = "deadline" if request.GET.get("sort") == "deadline" else ""
    order = (F("deadline").asc(nulls_last=True), "-first_seen_at", "-pk") if sort else ("-first_seen_at", "-pk")
    page = Paginator(query.select_related("source__organization").order_by(*order), 20).get_page(request.GET.get("page"))
    for job in page:
        job.days_left = (job.deadline - today).days if job.deadline else None
        job.is_new = job.first_seen_at >= timezone.now() - timedelta(days=3)
    return render(request, "board/jobs.html", {"page": page, **filters, "sort": sort, "employers": Organization.objects.filter(sources__jobs__in=visible).distinct().order_by("name"), "cities": visible.exclude(city="").values_list("city", flat=True).distinct().order_by("city"), "types": [(value, label) for value, label in Job.TYPE if visible.filter(opportunity_type=value).exists()]})


def sources(request):
    organizations = Organization.objects.prefetch_related("sources").order_by("name")
    today = timezone.localdate()
    cutoff = timezone.now() - timedelta(days=30)
    published = visible_jobs()
    counts = dict(published.values("source_id").annotate(total=Count("id")).values_list("source_id", "total"))
    review_counts = dict(Job.objects.filter(status="review", source__enabled=True).filter(Q(deadline__gte=today) | Q(deadline__isnull=True, first_seen_at__gte=cutoff)).values("source_id").annotate(total=Count("id")).values_list("source_id", "total"))
    rows = []
    totals = {"available": 0, "empty": 0, "review": 0, "partial": 0, "unavailable": 0, "pending": 0}
    for organization in organizations:
        for source in organization.sources.all() or [None]:
            last_check_failed = bool(source and source.last_attempt_at and (not source.last_success_at or source.last_attempt_at > source.last_success_at))
            # If the daily run stops, old counts must not keep reading as a healthy source.
            stale = bool(source and source.enabled and source.last_success_at and source.last_success_at < timezone.now() - STALE_AFTER)
            if source and (source.status in ("blocked", "failing") or last_check_failed or stale):
                status = "unavailable"
            elif source and source.enabled and source.status == "verified" and source.last_success_at:
                status = "partial" if (source.adapter_config or {}).get("partial_listing") else "available" if counts.get(source.pk, 0) else "review" if review_counts.get(source.pk, 0) else "empty"
            else:
                status = "pending"
            totals[status] += 1
            url = source.url if source else organization.website
            rows.append({"organization": organization, "source": source, "status": status, "count": counts.get(source.pk, 0) if source else 0, "review_count": review_counts.get(source.pk, 0) if source else 0, "url": url, "domain": urlsplit(url).hostname if url else ""})
    selected = request.GET.get("status", "all")
    if selected not in (*totals, "all"):
        selected = "all"
    visible_rows = rows if selected == "all" else [row for row in rows if row["status"] == selected]
    latest = Source.objects.filter(last_success_at__isnull=False).order_by("-last_success_at").values_list("last_success_at", flat=True).first()
    return render(request, "board/sources.html", {"rows": visible_rows, "total": len(rows), "organizations_total": organizations.count(), "shown": len(visible_rows), "totals": totals, "selected": selected, "open_jobs": published.count(), "latest": latest})


def health(request):
    return HttpResponse("ok", content_type="text/plain")


def scrape_health(request):
    """For external monitoring. /health/ stays a liveness check because the scheduler container waits on it."""
    stale = Source.objects.filter(enabled=True).exclude(adapter="none").filter(Q(last_success_at__isnull=True) | Q(last_success_at__lt=timezone.now() - STALE_AFTER))
    names = list(stale.values_list("url", flat=True)[:20])
    return HttpResponse("ok" if not names else "stale:\n" + "\n".join(names), content_type="text/plain", status=200 if not names else 503)
