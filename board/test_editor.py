from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .dedup import reconcile_aggregator_duplicates
from .models import Job, Organization, Source
from .views import past_job_query, visible_jobs


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class EditorTests(TestCase):
    def setUp(self):
        org = Organization.objects.create(name="UNDP u Bosni i Hercegovini", kind="international")
        self.source = Source.objects.create(organization=org, url="https://employer.test/jobs", adapter="oracle", enabled=True)
        self.job = Job.objects.create(
            source=self.source, canonical_url="https://employer.test/job/42", title="Project Officer",
            city="Sarajevo", deadline=timezone.localdate() + timedelta(days=10),
            status="review", content_hash="hash-v1", field_evidence={"review_reason": "Godina objave nije potvrđena"},
        )
        self.user = get_user_model().objects.create_user("editor", password="example", is_staff=True)

    def form_data(self, **extra):
        data = {
            "content_hash": self.job.content_hash, "title": self.job.title, "city": self.job.city,
            "deadline": self.job.deadline.isoformat(), "source_published_at": "",
            "application_url": "", "location_evidence": "Sarajevo, Bosnia and Herzegovina",
            "eligibility": "", "review_note": "Aktuelan na službenoj stranici poslodavca.",
            "confirmed": "on", "decision": "publish",
        }
        data.update(extra)
        return data

    def test_staff_only_dashboard_explains_automatic_publication(self):
        self.assertEqual(self.client.get("/editor/").status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get("/editor/")
        self.assertContains(response, "Potvrđeni oglasi se objavljuju automatski")
        self.assertContains(response, "Project Officer")

    def test_publish_requires_evidence_and_records_decision(self):
        self.client.force_login(self.user)
        response = self.client.post(f"/editor/jobs/{self.job.pk}/", self.form_data(confirmed=""))
        self.assertContains(response, "Potvrdite provjeru")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "review")
        response = self.client.post(f"/editor/jobs/{self.job.pk}/", self.form_data(title="Senior Project Officer"))
        self.assertRedirects(response, "/editor/", fetch_redirect_response=False)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "published")
        self.assertIsNotNone(self.job.published_at)
        self.assertIn("title", self.job.manually_edited_fields)
        self.assertEqual(self.job.field_evidence["editorial_note"], "Aktuelan na službenoj stranici poslodavca.")

    def test_stale_page_cannot_publish_and_rejection_needs_reason(self):
        self.client.force_login(self.user)
        self.job.content_hash = "hash-v2"
        self.job.save(update_fields=["content_hash"])
        self.assertRedirects(self.client.post(f"/editor/jobs/{self.job.pk}/", self.form_data(content_hash="hash-v1")), f"/editor/jobs/{self.job.pk}/", fetch_redirect_response=False)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "review")
        response = self.client.post(f"/editor/jobs/{self.job.pk}/", self.form_data(content_hash="hash-v2", decision="reject", review_note=""))
        self.assertContains(response, "Upišite razlog odbacivanja")
        self.client.post(f"/editor/jobs/{self.job.pk}/", self.form_data(content_hash="hash-v2", decision="reject", review_note="Nije rad u BiH."))
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.closed_reason), ("closed", "manual"))

    def test_duplicate_is_blocked_and_reconciled_out_of_queue(self):
        portal = Organization.objects.create(name="Impactpool", kind="aggregator")
        source = Source.objects.create(organization=portal, url="https://impactpool.test/jobs", adapter="impactpool", enabled=True)
        copy = Job.objects.create(
            source=source, canonical_url="https://impactpool.test/jobs/123",
            application_url="https://employer.test/job/42?utm_source=impactpool",
            title=self.job.title, city=self.job.city, deadline=self.job.deadline,
            status="review", content_hash="copy-v1", field_evidence={"review_reason": "Godina objave nije potvrđena"},
        )
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get("/editor/"), "/editor/jobs/%s/" % copy.pk)
        data = self.form_data(content_hash="copy-v1")
        self.assertContains(self.client.post(f"/editor/jobs/{copy.pk}/", data), "Duplikat službenog oglasa")
        self.assertEqual(reconcile_aggregator_duplicates(), 1)
        copy.refresh_from_db()
        self.assertEqual((copy.status, copy.closed_reason), ("closed", "duplicate"))
        self.assertEqual(copy.field_evidence["duplicate_of"], self.job.pk)
        self.assertEqual(reconcile_aggregator_duplicates(), 0)
        self.assertFalse(past_job_query(visible_jobs()).filter(pk=copy.pk).exists())
