from django.contrib import admin
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from django.utils.html import format_html
from .models import Job, Organization, ScrapeRun, Source, SourceDocument


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "country", "city", "verified_at")
    list_filter = ("kind", "city")
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


@admin.action(description="Objavi odabrane oglase")
def publish_jobs(modeladmin, request, queryset):
    expired = queryset.filter(deadline__lt=timezone.localdate()).count()
    disabled = queryset.filter(source__enabled=False).exclude(deadline__lt=timezone.localdate()).count()
    queryset.filter(source__enabled=True).exclude(deadline__lt=timezone.localdate()).update(status="published", closed_reason="", last_reviewed_at=timezone.now())
    if expired:
        modeladmin.message_user(request, f"{expired} oglas(a) nije objavljeno jer je rok istekao.", level="warning")
    if disabled:
        modeladmin.message_user(request, f"{disabled} oglas(a) nije objavljeno jer je izvor isključen.", level="warning")


@admin.action(description="Zatvori odabrane oglase")
def close_jobs(modeladmin, request, queryset):
    queryset.update(status="closed", closed_reason="manual", last_reviewed_at=timezone.now())


@admin.action(description="Obnovi provjeru oglasa bez roka")
def renew_jobs(modeladmin, request, queryset):
    queryset.filter(deadline__isnull=True).update(last_reviewed_at=timezone.now())


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
    readonly_fields = ("first_seen_at", "last_seen_at", "content_hash", "raw_text", "field_evidence", "missing_scans")

    @admin.display(description="Organizacija")
    def organization(self, obj):
        return obj.source.organization

    @admin.display(description="Razlog provjere")
    def review_reason(self, obj):
        return obj.field_evidence.get("review_reason", "") if obj.status == "review" else ""

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
    readonly_fields = ("source", "started_at", "finished_at", "success", "candidates", "error")

    def has_add_permission(self, request):
        return False


@admin.register(SourceDocument)
class SourceDocumentAdmin(admin.ModelAdmin):
    list_display = ("source", "url", "fetched_at", "content_hash")
    readonly_fields = ("source", "url", "fetched_at", "content_hash", "text")

    def has_add_permission(self, request):
        return False
