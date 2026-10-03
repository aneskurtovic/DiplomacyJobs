import difflib
import re

from django.contrib import admin
from django.contrib.admin.models import CHANGE, LogEntry
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from .models import Job, Organization, ScrapeRun, Source, SourceDocument
from .text import bs_plural


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "country", "city", "verified_at", "recruitment_status", "recruitment_checked_at")
    list_filter = ("kind", "city", "recruitment_status")
    search_fields = ("name", "country")


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("organization", "adapter", "status", "enabled", "last_success_at", "consecutive_failures", "last_run")
    list_filter = ("adapter", "status", "enabled")
    search_fields = ("organization__name", "url")

    def get_queryset(self, request):
        latest = ScrapeRun.objects.filter(source=OuterRef("pk")).order_by("-started_at")
        return super().get_queryset(request).select_related("organization").annotate(run_success=Subquery(latest.values("success")[:1]), run_candidates=Subquery(latest.values("candidates")[:1]), run_error=Subquery(latest.values("error")[:1]))

    @admin.display(description="Posljednje pokretanje")
    def last_run(self, obj):
        if obj.run_success is None:
            return "—"
        return f"{obj.run_candidates} kandidata" if obj.run_success else f"Greška: {obj.run_error[:120]}"


def log_bulk(request, pks, message):
    """Record a bulk action in each job's admin history, which QuerySet.update() skips."""
    if request is not None and pks:
        LogEntry.objects.log_actions(request.user.pk, Job.objects.filter(pk__in=pks), CHANGE, change_message=message)


@admin.action(description="Objavi odabrane oglase")
def publish_jobs(modeladmin, request, queryset):
    expired = queryset.filter(deadline__lt=timezone.localdate()).count()
    disabled = queryset.filter(source__enabled=False).exclude(deadline__lt=timezone.localdate()).count()
    publishable = queryset.filter(source__enabled=True).exclude(deadline__lt=timezone.localdate())
    # A job whose scan raised a review reason is published one at a time from its own page, never in bulk.
    flagged = [(pk, title, evidence["review_reason"]) for pk, title, evidence in publishable.values_list("pk", "title", "field_evidence") if (evidence or {}).get("review_reason")]
    published = list(publishable.exclude(pk__in=[pk for pk, _, _ in flagged]).values_list("pk", flat=True))
    Job.objects.filter(pk__in=published).update(status="published", closed_reason="", last_reviewed_at=timezone.now())
    log_bulk(request, published, "Objavljeno skupnom akcijom.")
    if flagged:
        names = "; ".join(f"{title} ({reason})" for _, title, reason in flagged[:5]) + (" …" if len(flagged) > 5 else "")
        modeladmin.message_user(request, f"{len(flagged)} {bs_plural(len(flagged), 'oglas nije objavljen', 'oglasa nisu objavljena', 'oglasa nije objavljeno')} jer čeka pregled; otvorite oglas i objavite ga pojedinačno: {names}", level="warning")
    if expired:
        modeladmin.message_user(request, f"{expired} {bs_plural(expired, 'oglas nije objavljen', 'oglasa nisu objavljena', 'oglasa nije objavljeno')} jer je rok istekao.", level="warning")
    if disabled:
        modeladmin.message_user(request, f"{disabled} {bs_plural(disabled, 'oglas nije objavljen', 'oglasa nisu objavljena', 'oglasa nije objavljeno')} jer je izvor isključen.", level="warning")


@admin.action(description="Zatvori odabrane oglase")
def close_jobs(modeladmin, request, queryset):
    closed = list(queryset.values_list("pk", flat=True))
    Job.objects.filter(pk__in=closed).update(status="closed", closed_reason="manual", last_reviewed_at=timezone.now())
    log_bulk(request, closed, "Zatvoreno skupnom akcijom.")


@admin.action(description="Obnovi provjeru oglasa bez roka")
def renew_jobs(modeladmin, request, queryset):
    renewed = list(queryset.filter(deadline__isnull=True).values_list("pk", flat=True))
    Job.objects.filter(pk__in=renewed).update(last_reviewed_at=timezone.now())
    log_bulk(request, renewed, "Provjera obnovljena skupnom akcijom.")


class DeadlineFilter(admin.SimpleListFilter):
    title = "rok"
    parameter_name = "rok"

    def lookups(self, request, model_admin):
        return [("open", "Aktuelan"), ("past", "Istekao"), ("none", "Bez roka")]

    def queryset(self, request, queryset):
        today = timezone.localdate()
        return {"open": queryset.filter(deadline__gte=today), "past": queryset.filter(deadline__lt=today), "none": queryset.filter(deadline__isnull=True)}.get(self.value(), queryset)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "city", "deadline", "source_published_at", "status", "review_reason", "official_link", "last_checked_at")
    list_filter = ("status", DeadlineFilter, "closed_reason", "opportunity_type", "source__organization")
    search_fields = ("title", "source__organization__name", "canonical_url")
    actions = (publish_jobs, close_jobs, renew_jobs)
    readonly_fields = ("first_seen_at", "last_seen_at", "source_changes", "content_hash", "raw_text", "field_evidence", "missing_scans")

    @admin.display(description="Organizacija")
    def organization(self, obj):
        return obj.employer_name

    @admin.display(description="Razlog provjere")
    def review_reason(self, obj):
        return obj.field_evidence.get("review_reason", "") if obj.status == "review" else ""

    @admin.display(description="Promjene izvora")
    def source_changes(self, obj):
        """What changed between the last two stored snapshots of the job's page, so a reviewer of a changed source does not compare texts by eye."""
        texts = list(SourceDocument.objects.filter(source_id=obj.source_id, url=obj.canonical_url).order_by("-fetched_at", "-pk").values_list("text", "fetched_at")[:2])
        if len(texts) < 2:
            return "Nema ranije verzije."
        (new, new_at), (old, old_at) = texts
        lines = [line for line in difflib.unified_diff(re.split(r"(?<=[.!?])\s+", old), re.split(r"(?<=[.!?])\s+", new), lineterm="", n=0) if line[:1] in "+-" and line[:3] not in ("+++", "---")]
        if not lines:
            return "Tekst se nije promijenio."
        rows = format_html_join("", '<div style="white-space:pre-wrap;color:{}">{}</div>', (("#1d6b45" if line[0] == "+" else "#a23b2a", line[:600]) for line in lines[:60]))
        return format_html("<p>{} → {}</p>{}", old_at.strftime("%d.%m.%Y."), new_at.strftime("%d.%m.%Y."), rows)

    @admin.display(description="Oglas")
    def official_link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">Otvori ↗</a>', obj.canonical_url)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("source__organization")

    def save_model(self, request, obj, form, change):
        if change:
            obj.manually_edited_fields = sorted(set(obj.manually_edited_fields) | set(form.changed_data))
            obj.last_reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(ScrapeRun)
class ScrapeRunAdmin(admin.ModelAdmin):
    list_display = ("source", "started_at", "success", "candidates", "error")
    list_filter = ("success", "source__adapter")
    search_fields = ("source__url", "source__organization__name", "error")
    date_hierarchy = "started_at"
    readonly_fields = ("source", "started_at", "finished_at", "success", "candidates", "error")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("source__organization")

    def has_add_permission(self, request):
        return False


@admin.register(SourceDocument)
class SourceDocumentAdmin(admin.ModelAdmin):
    list_display = ("source", "url", "fetched_at", "content_hash")
    list_filter = ("source__adapter",)
    search_fields = ("url", "source__organization__name")
    date_hierarchy = "fetched_at"
    readonly_fields = ("source", "url", "fetched_at", "content_hash", "text")

    def get_queryset(self, request):
        # Snapshot texts run to 100k characters; the list shows none of them.
        queryset = super().get_queryset(request).select_related("source__organization")
        return queryset if request.resolver_match and request.resolver_match.url_name.endswith("_change") else queryset.defer("text")

    def has_add_permission(self, request):
        return False
