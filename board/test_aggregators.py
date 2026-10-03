from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from django.test import TestCase, override_settings
from django.utils import timezone

from .aggregators import make_candidate
from .dedup import same_vacancy, url_key
from .ingest import fetch
from .models import Job, Organization, Source
from .views import visible_jobs


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class DedupTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="UNDP u Bosni i Hercegovini", kind="international")
        self.official = Source.objects.create(organization=self.org, adapter="oracle", url="https://employer.test/jobs", enabled=True)
        portal = Organization.objects.create(name="Impactpool", kind="international")
        self.portal = Source.objects.create(organization=portal, adapter="impactpool", url="https://www.impactpool.org/search", enabled=True)
        self.deadline = timezone.localdate() + timedelta(days=10)

    def job(self, source=None, **fields):
        values = dict(source=source or self.official, canonical_url="https://employer.test/job/42", title="Project Officer", city="Sarajevo", deadline=self.deadline, status="published")
        values.update(fields)
        return Job.objects.create(**values)

    def copy(self, **fields):
        defaults = dict(canonical_url="https://www.impactpool.org/jobs/123", application_url="https://employer.test/job/42?utm_source=impactpool", field_evidence={"employer_name": "UNDP - United Nations Development Programme"})
        defaults.update(fields)
        return self.job(self.portal, **defaults)

    def test_original_wins_in_either_ingestion_order_and_deadline_disagreement(self):
        copy = self.copy(deadline=self.deadline + timedelta(days=1))
        original = self.job()
        self.assertEqual(list(visible_jobs()), [original])
        self.assertEqual(Job.objects.count(), 2)
        self.assertContains(self.client.get("/"), "Project Officer", count=2)  # title and accessible link
        self.assertEqual(self.client.get("/feed/").content.count(b"<entry>"), 1)
        self.assertTrue(Job.objects.filter(pk=copy.pk).exists())

    def test_closed_or_reviewed_official_record_blocks_syndicated_resurrection(self):
        original = self.job(status="closed", closed_reason="withdrawn")
        self.copy()
        self.assertFalse(visible_jobs().exists())
        original.status = "review"
        original.save()
        self.assertFalse(visible_jobs().exists())

    def test_exact_fallback_requires_employer_city_and_deadline(self):
        original = self.job()
        copy = self.copy(application_url="")
        self.assertTrue(same_vacancy(original, copy))
        for field, value in [("deadline", self.deadline + timedelta(days=1)), ("city", "Mostar"), ("field_evidence", {"employer_name": "UNICEF"}), ("title", "Senior Project Officer")]:
            old = getattr(copy, field)
            setattr(copy, field, value)
            self.assertFalse(same_vacancy(original, copy), field)
            setattr(copy, field, old)

    def test_repeated_recruitment_rounds_are_separate(self):
        original = self.job(source_published_at=timezone.localdate() - timedelta(days=90))
        copy = self.copy(source_published_at=timezone.localdate())
        self.assertFalse(same_vacancy(original, copy))

    def test_job_ids_survive_and_generic_application_pages_do_not_match(self):
        self.assertNotEqual(url_key("https://ats.test/job?id=1"), url_key("https://ats.test/job?id=2"))
        self.assertEqual(url_key("https://jobs.unicef.org/cw/en-us/job/596053/long-title?utm_source=x"), url_key("https://jobs.unicef.org/en-us/job/596053"))
        original = self.job(application_url="https://ats.test/careers")
        copy = self.copy(title="Another position", application_url="https://ats.test/careers")
        self.assertFalse(same_vacancy(original, copy))

    def test_aggregator_employer_search_filter_and_feed(self):
        self.copy()
        self.assertContains(self.client.get("/", {"q": "UNDP"}), "Project Officer")
        self.assertContains(self.client.get("/", {"employer": self.org.pk}), "Project Officer")
        self.assertContains(self.client.get("/feed/", {"employer": self.org.pk}), "UNDP - United Nations Development Programme")
        self.assertNotContains(self.client.get("/", {"q": "Impactpool"}), "Project Officer")

    def test_unknown_employer_has_its_own_filter(self):
        self.copy(field_evidence={"employer_name": "International Detention Coalition"})
        self.assertContains(self.client.get("/", {"employer": "name:International Detention Coalition"}), "Project Officer")
        self.assertNotContains(self.client.get("/", {"employer": self.org.pk}), "Project Officer")


RELIEFWEB_JOB = """<html><body><nav>menu</nav><article class="node--job"><header class="rw-article__header">
<h1>Europe Programme Officer - Balkans</h1>
<dd class="rw-entity-meta__tag-value--source">International Detention Coalition</dd>
<dd class="rw-entity-meta__tag-value--posted"><time datetime="2026-09-22T07:30:02+00:00">22 Sep 2026</time></dd>
<dd class="rw-entity-meta__tag-value--closing"><time datetime="2026-10-16T00:00:00+00:00">16 Oct 2026</time></dd></header>
<div class="rw-article__content">The officer must be based in one of Albania or Bosnia and Herzegovina.</div>
<section class="rw-how-to-apply"><a href="https://idc.bamboohr.com/careers/47?utm_source=reliefweb">IDC careers</a></section>
<footer class="rw-article__footer"><section id="details"><dd class="rw-entity-meta__tag-value--country">
<a href="/country/alb">Albania</a><a href="/country/bih">Bosnia and Herzegovina</a></dd></section></footer></article></body></html>"""

IMPACTPOOL_JOB = """<html><body><div id="job-description"><div><h1>Project Manager</h1>
<span type="bodyEmphasis">UNDP - United Nations Development Programme</span><span type="body">Sarajevo</span>
<span>Application deadline: October 09, 2026 (5 days)</span></div><p>Background</p></div></body></html>"""


class AggregatorAdapterTests(TestCase):
    def http(self, routes):
        def handle(request):
            status, body, headers = routes[str(request.url)]
            return httpx.Response(status, content=body.encode(), headers={"content-type": "text/html", **headers}, request=request)
        return httpx.Client(transport=httpx.MockTransport(handle))

    def test_reliefweb_country_tags_in_article_footer_survive_fetch(self):
        url = "https://reliefweb.int/job/4230833/europe-programme-officer-balkans"
        source = SimpleNamespace(adapter="reliefweb", url="https://reliefweb.int/jobs", adapter_config={})
        with self.http({url: (200, RELIEFWEB_JOB, {})}) as client, patch("board.aggregators.timezone.localdate", return_value=date(2026, 10, 3)):
            self.assertIsNone(fetch(client, url)[1].select_one("footer"))  # other adapters keep stripping layout
            candidate = make_candidate(client, source, url, fetch(client, url, keep=("footer",))[1])
        self.assertTrue(candidate.eligible, candidate.reason)
        self.assertIn("Regionalna pozicija", candidate.eligibility)
        self.assertEqual((candidate.source_published_at, candidate.deadline), (date(2026, 9, 22), date(2026, 10, 16)))
        self.assertEqual(candidate.employer_name, "International Detention Coalition")
        self.assertEqual(candidate.external_id, "4230833")

    def test_reliefweb_multi_country_without_bih_residence_is_not_eligible(self):
        url = "https://reliefweb.int/job/1/x"
        source = SimpleNamespace(adapter="reliefweb", url="https://reliefweb.int/jobs", adapter_config={})
        html = RELIEFWEB_JOB.replace("Albania or Bosnia and Herzegovina", "Tirana, Albania")
        with self.http({url: (200, html, {})}) as client, patch("board.aggregators.timezone.localdate", return_value=date(2026, 10, 3)):
            candidate = make_candidate(client, source, url, fetch(client, url, keep=("footer",))[1])
        self.assertFalse(candidate.eligible)

    def test_impactpool_original_url_dedupes_oracle_requisition_variant(self):
        url = "https://www.impactpool.org/jobs/696031"
        oracle = "https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions/job/36935?utm_medium=referral&utm_source=impactpool"
        source = SimpleNamespace(adapter="impactpool", url="https://www.impactpool.org/search", adapter_config={})
        routes = {url: (200, IMPACTPOOL_JOB, {}), url + "/apply": (302, "", {"location": oracle})}
        with self.http(routes) as client, patch("board.aggregators.timezone.localdate", return_value=date(2026, 10, 3)):
            candidate = make_candidate(client, source, url, fetch(client, url, keep=("footer",))[1])
        self.assertEqual((candidate.city, candidate.deadline, candidate.source_published_at), ("Sarajevo", date(2026, 10, 9), None))
        self.assertFalse(candidate.year_proven)  # Impactpool shows no publication date; never invent one
        self.assertEqual(url_key(candidate.application_url), url_key("https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/36935"))
        self.assertNotEqual(url_key(candidate.application_url), url_key("https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/36935"))
