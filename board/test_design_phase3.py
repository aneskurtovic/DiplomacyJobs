"""Design system Phase 3: grouped /sources/, employer monograms and per-job share images."""
import io
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .models import Job, Organization, Source
from .text import monogram

STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


def tracked(name, **kwargs):
    organization = Organization.objects.create(name=name, kind="embassy", **kwargs)
    return Source.objects.create(organization=organization, url=f"https://{organization.pk}.example/jobs", adapter="generic", status="verified", enabled=True, last_success_at=timezone.now())


@override_settings(STORAGES=STATIC)
class SourcesPageTests(TestCase):
    def setUp(self):
        for number in range(7):
            tracked(f"Embassy Empty {number}")
        self.with_jobs = tracked("Mission With Jobs")
        Job.objects.create(source=self.with_jobs, canonical_url="https://jobs.example/1", title="Driver", status="published", deadline=timezone.localdate() + timedelta(days=5))
        Organization.objects.create(name="Ambasada Švicarske", kind="embassy", recruitment_status="not_found", recruitment_checked_at=timezone.localdate(), recruitment_evidence_url="https://ch.example", recruitment_notes="No list.")

    def test_full_list_groups_rows_with_jobs_first_and_trims_long_groups(self):
        response = self.client.get("/sources/")
        groups = response.context["groups"]
        self.assertEqual([group["state"] for group in groups], ["available", "empty", "not_found"])
        empty = groups[1]
        self.assertEqual((len(empty["rows"]), empty["total"], empty["hidden"]), (5, 7, 2))
        self.assertContains(response, 'href="?status=empty"')
        self.assertContains(response, "Prikaži sve (7)")
        buckets = {bucket["key"]: bucket["count"] for bucket in response.context["buckets"]}
        self.assertEqual(buckets, {"covered": 8, "partial": 0, "unavailable": 0, "untracked": 1})
        self.assertContains(response, "1 s oglasima · 7 bez oglasa")

    def test_card_filter_shows_every_row_of_its_states(self):
        response = self.client.get("/sources/", {"status": "covered"})
        self.assertEqual(response.context["shown"], 8)
        self.assertEqual(sum(len(group["rows"]) for group in response.context["groups"]), 8)
        current = [bucket for bucket in response.context["buckets"] if bucket["current"]]
        self.assertEqual([bucket["key"] for bucket in current], ["covered"])
        # The selected card links back to the full list.
        self.assertEqual(current[0]["query"], "")
        self.assertNotContains(response, "Ambasada Švicarske")

    def test_name_search_ignores_case_and_diacritics_and_keeps_the_card(self):
        response = self.client.get("/sources/", {"q": "svicarske"})
        self.assertEqual([row["organization"].name for group in response.context["groups"] for row in group["rows"]], ["Ambasada Švicarske"])
        self.assertEqual(self.client.get("/sources/", {"q": "svicarske", "status": "covered"}).context["shown"], 0)
        self.assertContains(self.client.get("/sources/", {"q": "nothing like it"}), "Nijedna organizacija ne odgovara pretrazi.")

    def test_unknown_status_falls_back_to_all(self):
        self.assertEqual(self.client.get("/sources/", {"status": "bogus"}).context["shown"], 9)


class MonogramTests(TestCase):
    def test_short_name_then_acronym_then_initials(self):
        self.assertEqual(monogram("Misija OSCE-a u Bosni i Hercegovini", "OSCE"), "OSCE")
        self.assertEqual(monogram("UNICEF - United Nations Children’s Fund"), "UNICEF")
        self.assertEqual(monogram("Misija OSCE-a u Bosni i Hercegovini"), "OSCE")
        self.assertEqual(monogram("International Detention Coalition"), "ID")
        self.assertEqual(monogram("Ambasada Italije u BiH"), "IT")

    def test_registry_import_sets_short_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            path.write_text(json.dumps([{"name": "UNDP u BiH", "short_name": "UNDP", "kind": "international", "sources": []}]), encoding="utf-8")
            call_command("import_registry", str(path), stdout=io.StringIO())
        self.assertEqual(Organization.objects.get().short_name, "UNDP")


@override_settings(STORAGES=STATIC)
class JobCardMonogramTests(TestCase):
    def test_card_uses_registry_short_name_and_syndicated_employer(self):
        source = tracked("UNFPA u Bosni i Hercegovini", short_name="UNFPA")
        Organization.objects.create(name="UN Women u Bosni i Hercegovini", kind="international", short_name="UNW")
        aggregator = Source.objects.create(organization=Organization.objects.create(name="ReliefWeb", kind="aggregator", short_name="RW"), url="https://reliefweb.example", adapter="generic", status="verified", enabled=True, last_success_at=timezone.now(), adapter_config={"portal_name": "ReliefWeb"})
        deadline = timezone.localdate() + timedelta(days=9)
        Job.objects.create(source=source, canonical_url="https://jobs.example/1", title="Analyst", status="published", deadline=deadline)
        Job.objects.create(source=aggregator, canonical_url="https://jobs.example/2", title="Expert", status="published", deadline=deadline, field_evidence={"employer_name": "UN Women u Bosni i Hercegovini"})
        page = self.client.get("/").content.decode()
        self.assertIn('<span class="monogram monogram-long" aria-hidden="true">UNFPA</span>', page)
        self.assertIn('<span class="monogram" aria-hidden="true">UNW</span>', page)
        self.assertNotIn(">RW</span>", page)


@override_settings(STORAGES=STATIC)
class ShareImageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.source = tracked("Ambasada Sjedinjenih Američkih Država u BiH")
        self.job = Job.objects.create(source=self.source, canonical_url="https://jobs.example/1", title="Električar – nadzornik " * 6, city="Sarajevo", status="published", deadline=timezone.localdate() + timedelta(days=4))

    def test_published_job_has_a_1200_by_630_png_and_og_tags(self):
        response = self.client.get(f"/jobs/{self.job.pk}/share.png")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("max-age=86400", response["Cache-Control"])
        self.assertEqual(Image.open(io.BytesIO(response.content)).size, (1200, 630))
        page = self.client.get(self.job.get_absolute_url()).content.decode()
        self.assertIn(f'<meta property="og:image" content="http://testserver/jobs/{self.job.pk}/share.png">', page)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', page)
        self.assertIn('<meta property="og:description" content="Električar', page)
        self.assertIn("Sarajevo. Rok:", page.split('property="og:description"')[1].split(">")[0])
        self.assertEqual(self.client.get(f"/en/jobs/{self.job.pk}/share.png").status_code, 200)

    def test_unpublished_job_has_no_image_and_an_expired_one_no_tag(self):
        review = Job.objects.create(source=self.source, canonical_url="https://jobs.example/2", title="Lead", status="review")
        self.assertEqual(self.client.get(f"/jobs/{review.pk}/share.png").status_code, 404)
        Job.objects.filter(pk=self.job.pk).update(deadline=timezone.localdate() - timedelta(days=1))
        self.assertNotContains(self.client.get(self.job.get_absolute_url()), "og:image")
