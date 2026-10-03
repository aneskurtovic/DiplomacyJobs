from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Job, Organization, Source


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class RecruitmentCoverageTests(TestCase):
    def audited(self, name, status="not_found", **kwargs):
        return Organization.objects.create(name=name, kind="embassy", recruitment_status=status, recruitment_checked_at=timezone.localdate(), recruitment_evidence_url="https://official.example/evidence", recruitment_notes="Checked official mission and recruitment pages.", **kwargs)

    def test_discovery_is_distinct_from_successful_empty_scrape(self):
        self.audited("No list found")
        org = self.audited("Needs integration", "integration")
        Source.objects.create(organization=org, url="https://official.example/jobs", adapter="none", status="unsupported")
        response = self.client.get("/sources/")
        self.assertEqual(response.context["totals"]["not_found"], 1)
        self.assertEqual(response.context["totals"]["integration"], 1)
        self.assertEqual(response.context["totals"]["empty"], 0)
        self.assertEqual(response.context["totals"]["pending"], 0)
        self.assertContains(response, "Dokaz provjere")
        self.assertContains(response, "Pronalazak izvora:")
        self.assertNotContains(response, 'data-label="Otvoreni oglasi">0')
        filtered = self.client.get("/sources/", {"status": "not_found"})
        self.assertEqual([row["organization"].name for group in filtered.context["groups"] for row in group["rows"]], ["No list found"])
        self.assertFalse(Job.objects.exists())

    def test_missing_old_or_future_discovery_evidence_stays_pending(self):
        for name in ("Old", "Future", "Missing evidence", "No date"):
            self.audited(name)
        Organization.objects.filter(name="Old").update(recruitment_checked_at=timezone.localdate() - timedelta(days=91))
        Organization.objects.filter(name="Future").update(recruitment_checked_at=timezone.localdate() + timedelta(days=1))
        Organization.objects.filter(name="Missing evidence").update(recruitment_evidence_url="")
        Organization.objects.filter(name="No date").update(recruitment_checked_at=None)
        self.assertEqual(self.client.get("/sources/").context["totals"]["pending"], 4)

    def test_access_failure_without_source_is_unavailable_and_not_empty(self):
        self.audited("Blocked mission", "blocked")
        response = self.client.get("/sources/", {"status": "unavailable"})
        self.assertEqual(response.context["shown"], 1)
        self.assertEqual(response.context["totals"]["empty"], 0)
        self.assertContains(response, "Blocked mission")

    def test_actual_scrape_health_takes_precedence_over_discovery(self):
        org = self.audited("Now operational", "blocked")
        Source.objects.create(organization=org, url="https://official.example/jobs", adapter="generic", status="verified", enabled=True, last_success_at=timezone.now())
        response = self.client.get("/sources/")
        self.assertEqual(response.context["totals"]["empty"], 1)
        Source.objects.update(last_success_at=timezone.now() - timedelta(hours=49))
        self.assertEqual(self.client.get("/sources/").context["totals"]["unavailable"], 1)

    def test_replacement_only_hides_disabled_history_for_active_same_org_source(self):
        org = Organization.objects.create(name="OSCE", kind="international")
        replacement = Source.objects.create(organization=org, url="https://official.example/filtered", adapter="osce", status="verified", enabled=True, last_success_at=timezone.now())
        legacy = Source.objects.create(organization=org, url="https://official.example/", adapter_config={"superseded_by": replacement.url})
        job = Job.objects.create(source=legacy, title="Historical", canonical_url="https://official.example/old", status="closed")
        response = self.client.get("/sources/")
        self.assertEqual(response.context["total"], 1)
        self.assertTrue(Job.objects.filter(pk=job.pk).exists())
        replacement.enabled = False
        replacement.save()
        self.assertEqual(self.client.get("/sources/").context["total"], 2)
        replacement.enabled = True
        replacement.organization = Organization.objects.create(name="Different mission", kind="embassy")
        replacement.save()
        self.assertEqual(self.client.get("/sources/").context["total"], 2)
