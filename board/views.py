import hashlib
import ipaddress
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from django import forms
from django.contrib import messages
from django.core.mail import mail_admins
from django.core.paginator import InvalidPage, Paginator
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.urls import reverse, translate_url
from django.utils import timezone, translation
from django.utils.html import escape
from django.utils.translation import gettext, gettext_lazy as _
from . import requirements
from .models import Job, Organization, Report, Source
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
    education = params.get("edu", "")
    experience = params.get("exp", "")
    field = params.get("field", "")
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
    # Requirement filters answer "what can I apply for": jobs whose stated minimum is at or below the visitor's. A job that states no minimum is left out, because it is not known to match.
    if education in requirements.LEVEL_RANK:
        query = query.filter(education_level__in=[level for level, rank in requirements.LEVEL_RANK.items() if rank <= requirements.LEVEL_RANK[education]])
    else:
        education = ""
    if experience in EXPERIENCE_CHOICES:
        query = query.filter(experience_years__lte=int(experience))
    else:
        experience = ""
    if field in requirements.FIELD_LABELS:
        # JSON containment is not portable to SQLite; visible jobs are few.
        query = query.filter(pk__in=[pk for pk, fields in query.values_list("pk", "fields_of_study") if field in (fields or [])])
    else:
        field = ""
    return query, {"search": search, "employer": employer, "city": city, "kind": kind, "scope": scope, "education": education, "experience": experience, "field": field}


EXPERIENCE_CHOICES = {"0": _("Bez iskustva"), "2": _("Do 2 godine"), "5": _("Do 5 godina"), "10": _("Do 10 godina")}
FILTER_PARAMS = (("q", "search"), ("employer", "employer"), ("city", "city"), ("type", "kind"), ("scope", "scope"), ("edu", "education"), ("exp", "experience"), ("field", "field"))
REQUIREMENT_FILTERS = ("education", "experience", "field")


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
        annotate(job, today)
    # The feed takes the same filters, so the current search can be followed.
    feed_query = urlencode({key: filters[name] for key, name in FILTER_PARAMS if filters[name]})
    # Page links keep only the active filters and sort.
    page_query = "&".join(part for part in (feed_query, urlencode({"sort": sort}) if sort else "") if part)
    known = {employer_key(org.name): org for org in Organization.objects.all()}
    employers = {}
    for job in visible.select_related("source__organization").defer("raw_text"):
        key = employer_key(job.employer_name)
        employers[key] = known.get(key) or {"pk": "name:" + job.employer_name, "name": job.employer_name}
    return render(request, "board/jobs.html", {"page": page, **filters, "sort": sort, "feed_query": feed_query, "page_query": page_query, "employers": sorted(employers.values(), key=lambda item: item["name"] if isinstance(item, dict) else item.name), "cities": visible.exclude(city="").values_list("city", flat=True).distinct().order_by("city"), "types": [(value, label) for value, label in Job.TYPE if visible.filter(opportunity_type=value).exists()], "education_levels": requirements.EDUCATION_LEVELS, "experience_choices": EXPERIENCE_CHOICES.items(), "fields": fields_in(visible), "requirement_filter": any(filters[name] for name in REQUIREMENT_FILTERS)})


def annotate(job, today):
    job.days_left = (job.deadline - today).days if job.deadline else None
    job.is_new = job.first_seen_at >= timezone.now() - timedelta(days=3)
    job.tags = requirements.tags(job)
    found = translation_for(job)
    # A foreign-language title gets its translation underneath; an advert already in the interface language does not.
    job.translated_title = found["title"] if found and found["is_translation"] and fold(found["title"]) != fold(job.title) else ""


def fields_in(query):
    """Fields of study that at least one visible job asks for, in taxonomy order."""
    present = {slug for fields in query.values_list("fields_of_study", flat=True) for slug in (fields or [])}
    return [(slug, label) for slug, label, _ in requirements.FIELDS if slug in present]


def job_detail(request, pk, slug=None):
    """One job. Only published jobs have a public page; a closed one answers 410 without showing unreviewed details."""
    job = get_object_or_404(Job.objects.select_related("source__organization"), pk=pk)
    if job.status == "closed":
        return render(request, "board/job_gone.html", {"job": job}, status=410)
    if job.status != "published":
        raise Http404(gettext("Nema tog oglasa"))
    if slug != job.slug:
        return redirect(job.get_absolute_url(), permanent=True)
    annotate(job, timezone.localdate())
    # Published but expired, hidden as a duplicate, or from a disabled source: still readable, marked as not current.
    current = visible_jobs().filter(pk=job.pk).exists()
    return render(request, "board/job_detail.html", {"job": job, "current": current, "details": requirements.details(job), "terms": requirements.terms(job), "form": ReportForm(job=job), "translation": translation_for(job)})


class ReportForm(forms.Form):
    reason = forms.ChoiceField(label=_("Šta nije u redu?"), choices=Report.REASONS, widget=forms.RadioSelect)
    message = forms.CharField(label=_("Opis (neobavezno)"), required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 4, "placeholder": _("Npr. rok je produžen, link vodi na pogrešnu stranicu …")}))
    email = forms.EmailField(label=_("Vaš e-mail (neobavezno, samo ako želite odgovor)"), required=False)
    # Hidden from people; a bot that fills every field is ignored.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    JOB_REASONS = ("expired", "wrong_info", "broken_link", "not_bih", "duplicate", "suspicious", "other")
    SITE_REASONS = ("missing", "site", "wrong_info", "broken_link", "other")

    def __init__(self, *args, job=None, **kwargs):
        super().__init__(*args, **kwargs)
        labels = dict(Report.REASONS)
        self.fields["reason"].choices = [(value, labels[value]) for value in (self.JOB_REASONS if job else self.SITE_REASONS)]

    def clean(self):
        data = super().clean()
        if data.get("reason") == "other" and not (data.get("message") or "").strip():
            self.add_error("message", gettext("Opišite ukratko problem."))
        return data


REPORTS_PER_HOUR = 5


def client_hash(request):
    """A keyed hash of the visitor's address. Behind the host's reverse proxy (compose binds 127.0.0.1) the address is the last X-Forwarded-For hop, the one the proxy appended."""
    address = request.META.get("REMOTE_ADDR", "")
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    try:
        ip = ipaddress.ip_address(address)
        if forwarded and (ip.is_loopback or ip.is_private):
            address = forwarded.split(",")[-1].strip()
    except ValueError:
        pass
    return hashlib.sha256(f"{settings.SECRET_KEY}:report:{address}".encode()).hexdigest()


def report(request, pk=None):
    """Report a problem with a published job (pk) or with the site."""
    job = get_object_or_404(Job.objects.select_related("source__organization"), pk=pk, status="published") if pk is not None else None
    back = job.get_absolute_url() if job else reverse("jobs")
    page = (request.POST.get("page") or request.GET.get("page") or "")[:500]
    page = page if page.startswith("/") and not page.startswith("//") else ""
    if request.method == "POST":
        form = ReportForm(request.POST, job=job)
        if form.is_valid():
            if form.cleaned_data["website"]:
                messages.success(request, gettext("Hvala, prijava je zaprimljena."))
                return redirect(back)
            key = client_hash(request)
            if Report.objects.filter(client_hash=key, created_at__gte=timezone.now() - timedelta(hours=1)).count() >= REPORTS_PER_HOUR:
                form.add_error(None, gettext("Poslali ste više prijava u kratkom roku. Pokušajte ponovo za sat vremena."))
            else:
                item = Report.objects.create(job=job, reason=form.cleaned_data["reason"], message=form.cleaned_data["message"].strip(), email=form.cleaned_data["email"], page_url=page, client_hash=key)
                # Sent only when ADMINS and an e-mail backend are configured; the admin list is the record either way.
                mail_admins(f"Nova prijava: {item.get_reason_display()}", f"{item}\n\n{item.message}\n\n{absolute(request, f'/admin/board/report/{item.pk}/change/')}", fail_silently=True)
                messages.success(request, gettext("Hvala! Prijava je zaprimljena i pregledat ćemo je."))
                return redirect(back if job or not page else page)
    else:
        form = ReportForm(job=job)
    return render(request, "board/report.html", {"form": form, "job": job, "page": page})


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


def languages(request):
    """The current page in each interface language, for the switcher and hreflang links. Pages outside the language URLs (admin, feed) get none."""
    match = getattr(request, "resolver_match", None)
    if match is None or match.url_name not in LANGUAGE_PAGES:
        return {"language_links": []}
    current = translation.get_language()
    path = request.get_full_path()
    return {"language_links": [{"code": code, "name": name, "url": translate_url(path, code), "current": code == current} for code, name in settings.LANGUAGES]}


LANGUAGE_PAGES = {"jobs", "job", "job_short", "job_report", "report", "sources"}


def translation_for(job):
    """The advert's machine translation in the interface language, if one exists for its current text."""
    from .translation import current_translation
    return current_translation(job, translation.get_language())


def robots(request):
    lines = ["User-agent: *", "Disallow: /admin/", "Disallow: /health/", f"Sitemap: {absolute(request, '/sitemap.xml')}"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def sitemap(request):
    paths = []
    jobs = list(visible_jobs().only("pk", "title").order_by("pk"))
    for code, _name in settings.LANGUAGES:
        with translation.override(code):
            paths += [reverse("jobs"), reverse("sources"), *(job.get_absolute_url() for job in jobs)]
    urls = "".join(f"<url><loc>{escape(absolute(request, path))}</loc><changefreq>daily</changefreq></url>" for path in paths)
    return HttpResponse(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', content_type="application/xml")


def health(request):
    return HttpResponse("ok", content_type="text/plain")


def scrape_health(request):
    """For external monitoring. /health/ stays a liveness check because the scheduler container waits on it."""
    stale = Source.objects.filter(enabled=True).exclude(adapter="none").filter(Q(last_success_at__isnull=True) | Q(last_success_at__lt=timezone.now() - STALE_AFTER))
    names = list(stale.values_list("url", flat=True)[:20])
    return HttpResponse("ok" if not names else "stale:\n" + "\n".join(names), content_type="text/plain", status=200 if not names else 503)
