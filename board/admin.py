from django.contrib import admin
from django.utils import timezone
from .models import Job, Organization, ScrapeRun, Source, SourceDocument


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "country", "city", "verified_at")
    list_filter = ("kind", "city")
    search_fields = ("name", "country")


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("organization", "adapter", "status", "enabled", "last_success_at", "consecutive_failures")
    list_filter = ("adapter", "status", "enabled")
    search_fields = ("organization__name", "url")


@admin.action(description="Objavi odabrane oglase")
def publish_jobs(modeladmin, request, queryset):
    queryset.filter(source__enabled=True).update(status="published", last_reviewed_at=timezone.now())


@admin.action(description="Zatvori odabrane oglase")
def close_jobs(modeladmin, request, queryset):
    queryset.update(status="closed")


@admin.action(description="Obnovi provjeru oglasa bez roka")
def renew_jobs(modeladmin, request, queryset):
    queryset.filter(deadline__isnull=True).update(last_reviewed_at=timezone.now())


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "city", "deadline", "status", "last_checked_at")
    list_filter = ("status", "opportunity_type", "source__organization")
    search_fields = ("title", "source__organization__name", "canonical_url")
    actions = (publish_jobs, close_jobs, renew_jobs)
    readonly_fields = ("first_seen_at", "last_seen_at", "content_hash", "raw_text", "field_evidence", "missing_scans")

    @admin.display(description="Organizacija")
    def organization(self, obj):
        return obj.source.organization

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
