from datetime import timedelta
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from .models import Job, Organization, Source


def jobs(request):
    today = timezone.localdate()
    cutoff = timezone.now() - timedelta(days=30)
    query = Job.objects.filter(status="published", source__enabled=True).filter(Q(deadline__gte=today) | Q(deadline__isnull=True)).filter(Q(deadline__isnull=False) | Q(first_seen_at__gte=cutoff) | Q(last_reviewed_at__gte=cutoff))
    search = request.GET.get("q", "").strip()[:100]
    employer = request.GET.get("employer", "")
    city = request.GET.get("city", "")
    if search:
        query = query.filter(Q(title__icontains=search) | Q(source__organization__name__icontains=search))
    if employer.isdecimal() and len(employer) <= 18:
        query = query.filter(source__organization_id=int(employer))
    if city:
        query = query.filter(city=city[:100])
    page = Paginator(query.select_related("source__organization").order_by("-first_seen_at", "-pk"), 20).get_page(request.GET.get("page"))
    return render(request, "board/jobs.html", {"page": page, "search": search, "employer": employer, "city": city, "employers": Organization.objects.filter(sources__jobs__status="published").distinct().order_by("name"), "cities": Job.objects.filter(status="published").exclude(city="").values_list("city", flat=True).distinct().order_by("city")})


def sources(request):
    organizations = Organization.objects.prefetch_related("sources").order_by("name")
    return render(request, "board/sources.html", {"organizations": organizations, "total": organizations.count(), "operational": Source.objects.filter(enabled=True, status="verified").count()})


def health(request):
    return HttpResponse("ok", content_type="text/plain")
