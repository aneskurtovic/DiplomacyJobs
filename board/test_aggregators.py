from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone

from .dedup import same_vacancy, url_key
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
