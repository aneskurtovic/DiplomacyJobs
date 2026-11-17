from datetime import timedelta
from importlib import import_module
import json
from pathlib import Path
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from board.ingest import discover_links, ingest_source
from board.management.commands.scrape_jobs import due_sources
from board.models import Job, Organization, ScrapeRun, Source


GREEK_URL = "https://www.mfa.gr/bosnia-herzegovina/en/category/news/embassy-news/"
GREEK_CONFIG = {
    "allow_empty": True,
    "path_contains": "/bosnia-herzegovina/en/",
    "link_selector": ".module-post-news a[href]",
    "listing_selector": "main .module-post-news",
    "content_selector": "main article",
    "published_selector": "article p.text-sm",
    "page_item_selector": ".module-post-news .swiper-slide",
    "next_page_selector": "a.next.page-numbers",
    "stop_at_older_page": True,
}


def greek_page(title="NOTICE", year=2026, next_page=None):
    return BeautifulSoup(
        '<main><section class="module-post-news"><div class="swiper-slide">'
        f'<h4 class="date">October 25, {year}</h4>'
        f'<a href="/bosnia-herzegovina/en/post-{year}/"><h3>{title}</h3></a>'
        '</div></section>'
        + (f'<a class="next page-numbers" href="{next_page}">Next</a>' if next_page else '')
        + '</main>', "html.parser",
    )


class ScraperRecoveryTests(TestCase):
    def setUp(self):
        self.source = Source.objects.create(
            organization=Organization.objects.create(name="Test mission", kind="embassy"),
            url=GREEK_URL, adapter="generic", enabled=True, adapter_config=GREEK_CONFIG,
        )

    def test_greek_news_follows_path_pagination_and_stops_at_previous_year(self):
        next_page = GREEK_URL + "page/2/"
        pages = [greek_page("VACANCY: Driver", next_page=GREEK_URL + "page/3/"), greek_page(year=2025, next_page=GREEK_URL + "page/4/")]
        with patch("board.ingest.fetch", side_effect=[("", p) for p in pages]) as fetch:
            links = discover_links(None, self.source, greek_page(next_page=next_page))
        self.assertEqual(links, [("https://www.mfa.gr/bosnia-herzegovina/en/post-2026", "VACANCY: Driver")])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[0].args[1], next_page)

    def test_greek_changed_layout_cannot_become_successful_empty_scan(self):
        for html in ("<main>Maintenance</main>", '<main><section class="module-post-news"></section></main>'):
            with self.subTest(html=html), self.assertRaisesMessage(ValueError, "listing element missing"):
                discover_links(None, self.source, BeautifulSoup(html, "html.parser"))

    def test_greek_pagination_cannot_leave_official_listing(self):
        with patch("board.ingest.fetch") as fetch:
            with self.assertRaisesMessage(ValueError, "pagination URL"):
                discover_links(None, self.source, greek_page(next_page="https://other.example/page/2/"))
        fetch.assert_not_called()

    def test_greek_pagination_rejects_cycles_and_changed_second_page(self):
        next_page = GREEK_URL + "page/2/"
        for page, message in [(greek_page(next_page=next_page), "pagination URL"),
                              (BeautifulSoup("<main>Maintenance</main>", "html.parser"), "listing element missing")]:
            with self.subTest(message=message), patch("board.ingest.fetch", return_value=("", page)):
                with self.assertRaisesMessage(ValueError, message):
                    discover_links(None, self.source, greek_page(next_page=next_page))

    def test_greek_url_migration_preserves_identity_history_and_extra_settings(self):
        migration = import_module("board.migrations.0045_greek_news_source")
        self.source.url = migration.OLD_URL
        self.source.adapter_config = {**migration.OLD_CONFIG, "impersonate": True, "history": {}}
        self.source.consecutive_failures = 146
        self.source.save()
        job = Job.objects.create(source=self.source, canonical_url="https://www.mfa.gr/old-job", title="Driver")
        run = ScrapeRun.objects.create(source=self.source, error="HTTP 404")
        migration.forward(apps, None)
        self.source.refresh_from_db()
        self.assertEqual(self.source.url, GREEK_URL)
        self.assertEqual(self.source.consecutive_failures, 146)
        self.assertTrue(self.source.enabled)
        self.assertTrue(self.source.adapter_config["impersonate"])
        self.assertEqual(self.source.jobs.get().pk, job.pk)
        self.assertEqual(self.source.runs.get().pk, run.pk)
        registry = json.loads((Path(__file__).resolve().parent.parent / "data/source_registry.json").read_text(encoding="utf-8"))
        entry = next(s for org in registry for s in org.get("sources", []) if s["url"] == GREEK_URL)
        self.assertEqual(self.source.adapter_config, entry["adapter_config"])
        migration.backward(apps, None)
        self.source.refresh_from_db()
        self.assertEqual(self.source.url, migration.OLD_URL)
        self.assertNotIn("next_page_selector", self.source.adapter_config)

    def test_workday_scan_uses_api_without_rate_limited_html_request(self):
        self.source.adapter = "workday"
        self.source.url = "https://unhcr.wd3.myworkdayjobs.com/External"
        self.source.adapter_config = {"allow_empty": True}
        self.source.save()
        requests = []
        def handle(req):
            requests.append((req.method, req.url.path))
            if req.method == "POST" and req.url.path == "/wday/cxs/unhcr/External/jobs":
                return httpx.Response(200, json={"total": 1, "facets": [{"facetParameter": "locationCountry", "values": [{"id": "JP", "descriptor": "Japan"}]}]})
            return httpx.Response(429)
        client = httpx.Client(transport=httpx.MockTransport(handle))
        with patch("board.ingest.open_client", return_value=client):
            result = ingest_source(self.source.pk)
        self.assertTrue(result.success, result.error)
        self.assertEqual(requests, [("POST", "/wday/cxs/unhcr/External/jobs")])

    def test_scheduled_failures_back_off_and_success_restores_normal_interval(self):
        now = timezone.now()
        ScrapeRun.objects.create(source=self.source, started_at=now - timedelta(hours=2), finished_at=now, success=False)
        for failures, due in [(0, True), (1, True), (2, False), (10, False), (0, True)]:
            Source.objects.filter(pk=self.source.pk).update(consecutive_failures=failures)
            self.assertEqual(bool(list(due_sources(Source.objects.all(), now))), due, failures)
        Source.objects.filter(pk=self.source.pk).update(consecutive_failures=100)
        self.assertTrue(list(due_sources(Source.objects.all(), now + timedelta(hours=22))))

    def test_backoff_never_shortens_daily_procurement_interval(self):
        self.source.adapter = "undpnotices"
        self.source.consecutive_failures = 1
        self.source.save()
        now = timezone.now()
        ScrapeRun.objects.create(source=self.source, started_at=now - timedelta(hours=3), finished_at=now)
        self.assertEqual(list(due_sources(Source.objects.all(), now)), [])
