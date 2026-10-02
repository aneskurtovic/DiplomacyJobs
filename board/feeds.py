from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Atom1Feed

from .models import Job
from .views import filter_jobs, visible_jobs


class JobsFeed(Feed):
    """Newest published jobs; accepts the same filters as the board (q, employer, city, type, scope)."""
    feed_type = Atom1Feed
    title = "DiplomacyJobs – novi oglasi"
    link = "/"
    subtitle = "Provjereni oglasi diplomatskih misija i međunarodnih organizacija u Bosni i Hercegovini."

    def get_object(self, request):
        return request.GET

    def items(self, params):
        query, _ = filter_jobs(visible_jobs(), params)
        return query.select_related("source__organization").order_by("-first_seen_at", "-pk")[:50]

    def item_title(self, job):
        return f"{job.title} – {job.source.organization.name}"

    def item_description(self, job):
        deadline = job.deadline.strftime("%d.%m.%Y.") if job.deadline else "nije naveden"
        return f"{job.get_opportunity_type_display()} · {job.city or 'Bosna i Hercegovina'} · Rok: {deadline}"

    def item_link(self, job):
        return job.application_url or job.canonical_url

    def item_guid(self, job):
        return f"diplomacyjobs-job-{job.pk}"

    item_guid_is_permalink = False

    def item_pubdate(self, job):
        return job.first_seen_at
