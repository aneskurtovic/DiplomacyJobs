"""Employer pages, and the "same employer" and "similar positions" sections on the job page."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone, translation

from . import related
from .models import Job, Organization, Source

STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


def source(name, adapter="generic", **kwargs):
    organization = Organization.objects.create(name=name, kind="international", **kwargs)
    return Source.objects.create(organization=organization, url=f"https://{organization.pk}.example/jobs", adapter=adapter, status="verified", enabled=True, last_success_at=timezone.now())


def job(source, title, number, **kwargs):
    values = {"status": "published", "deadline": timezone.localdate() + timedelta(days=10), "city": "Sarajevo", "canonical_url": f"https://{source.pk}.example/jobs/{number}"}
    return Job.objects.create(source=source, title=title, **{**values, **kwargs})


@override_settings(STORAGES=STATIC)
class RelatedSectionTests(TestCase):
    def setUp(self):
        # URLs are built outside a request, in the active language; another test may have left English active.
        translation.activate("bs")
        self.addCleanup(translation.deactivate)
        self.undp = source("UNDP u Bosni i Hercegovini", short_name="UNDP")
        self.osce = source("Misija OSCE-a u Bosni i Hercegovini")
        self.embassy = source("Ambasada Japana")
        self.aggregator = source("Impactpool", adapter="impactpool")

    def test_sections_are_left_out_when_nothing_relates(self):
        alone = job(self.embassy, "Driver", 1)
        job(self.osce, "Senior Legal Officer", 2, fields_of_study=["law"])
        response = self.client.get(alone.get_absolute_url())
        self.assertEqual((response.context["employer_jobs"], response.context["similar_jobs"]), ([], []))
        self.assertNotContains(response, "Drugi oglasi istog poslodavca")
        self.assertNotContains(response, "Slične pozicije")
        self.assertNotContains(response, 'class="related-jobs"')

    def test_same_employer_counts_aggregator_copies_and_links_to_the_employer_page(self):
        main = job(self.undp, "Project Manager", 1)
        others = [job(self.undp, f"Project Associate {number}", number + 10) for number in range(3)]
        copy = job(self.aggregator, "Energy Analyst", 20, field_evidence={"employer_name": "UNDP - United Nations Development Programme"})
        response = self.client.get(main.get_absolute_url())
        shown = response.context["employer_jobs"]
        self.assertEqual(len(shown), 3)
        self.assertEqual(response.context["employer_jobs_total"], 4)
        self.assertIn(copy, shown)  # the newest, though it came through an aggregator
        self.assertNotIn(main, shown)
        self.assertContains(response, "Svi oglasi poslodavca (4)")
        self.assertContains(response, self.undp.organization.get_absolute_url())
        self.assertTrue(set(shown) <= {*others, copy})

    def test_similar_needs_a_shared_title_word_and_skips_the_same_employer(self):
        main = job(self.undp, "Monitoring and Evaluation Analyst", 1, fields_of_study=["economics", "statistics"], education_level="master")
        close = job(self.osce, "Evaluation Officer", 2, fields_of_study=["statistics"])
        job(self.embassy, "Chief of General Services", 3, fields_of_study=["economics", "statistics"], education_level="master")  # fields only
        job(self.undp, "Evaluation Associate", 4, fields_of_study=["statistics"])  # same employer
        job(self.osce, "Evaluation Assistant", 5, deadline=timezone.localdate() - timedelta(days=1))  # not current
        response = self.client.get(main.get_absolute_url())
        self.assertEqual(response.context["similar_jobs"], [close])
        self.assertContains(response, "Slične pozicije")

    def test_score_rules(self):
        main = job(self.undp, "Legal Expert, National Consultant", 1, opportunity_type="consultancy", fields_of_study=["law"])
        self.assertEqual(related.similarity(main, job(self.osce, "Expert for Data", 2, opportunity_type="consultancy")), 0)  # job-family word only
        self.assertGreaterEqual(related.similarity(main, job(self.osce, "Legal Adviser", 3, fields_of_study=["law"])), related.SIMILAR_THRESHOLD)
        self.assertEqual(related.stems("National Consultants [Open to internal and external candidates]"), related.stems("consultant"))
        self.assertEqual(related.stems("Évaluation"), related.stems("evaluator"))


@override_settings(STORAGES=STATIC)
class OrganizationPageTests(TestCase):
    def setUp(self):
        translation.activate("bs")
        self.addCleanup(translation.deactivate)
        self.unicef = source("UNICEF u Bosni i Hercegovini", website="https://unicef.example", recruitment_checked_at=timezone.localdate(), recruitment_evidence_url="https://unicef.example/careers", recruitment_notes="Listing on the global portal.")
        self.aggregator = source("Impactpool", adapter="impactpool")
        self.empty = source("Ambasada Japana")

    def test_lists_current_jobs_including_aggregator_copies_of_its_jobs(self):
        own = job(self.unicef, "Child Protection Officer", 1)
        copy = job(self.aggregator, "Education Consultant", 2, field_evidence={"employer_name": "UNICEF - United Nations Children’s Fund"})
        unknown = job(self.aggregator, "Programme Officer", 3, field_evidence={"employer_name": "Some Foundation"})
        response = self.client.get(self.unicef.organization.get_absolute_url())
        self.assertEqual(set(response.context["current_jobs"]), {own, copy})
        self.assertContains(response, "Listing on the global portal.")
        self.assertContains(response, "https://unicef.example/careers")
        self.assertNotContains(response, 'name="robots"')
        # An employer the registry does not know stays under the aggregator.
        self.assertEqual(self.client.get(self.aggregator.organization.get_absolute_url()).context["current_jobs"], [unknown])

    def test_past_jobs_are_once_published_and_not_closed_by_a_reviewer(self):
        expired = job(self.unicef, "Expired Post", 1, deadline=timezone.localdate() - timedelta(days=3))
        expired.status, expired.closed_reason = "closed", "deadline"
        expired.save()
        Job.objects.create(source=self.unicef.organization.sources.get(), canonical_url="https://x.example/never", title="Never Published", status="closed", closed_reason="deadline", deadline=timezone.localdate() - timedelta(days=3))
        manual = job(self.unicef, "Duplicate Closed By Reviewer", 3)
        manual.status, manual.closed_reason = "closed", "manual"
        manual.save()
        response = self.client.get(self.unicef.organization.get_absolute_url())
        self.assertEqual(list(response.context["past_page"]), [expired])
        self.assertContains(response, "Raniji oglasi")
        self.assertContains(response, "Trenutno nema otvorenih oglasa ove organizacije.")

    def test_past_aggregator_copy_of_an_own_job_is_left_out(self):
        own = job(self.unicef, "Health Specialist", 1, status="closed", closed_reason="deadline", deadline=timezone.localdate() - timedelta(days=2), published_at=timezone.now())
        job(self.aggregator, "Health Specialist", 2, status="closed", closed_reason="deadline", deadline=own.deadline, published_at=timezone.now(), canonical_url=own.canonical_url, field_evidence={"employer_name": "UNICEF - United Nations Children’s Fund"})
        self.assertEqual(list(self.client.get(self.unicef.organization.get_absolute_url()).context["past_page"]), [own])

    def test_page_without_jobs_is_not_indexed_and_past_section_is_hidden(self):
        response = self.client.get(self.empty.organization.get_absolute_url())
        self.assertContains(response, '<meta name="robots" content="noindex">')
        self.assertNotContains(response, "Raniji oglasi")
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn(self.empty.organization.get_absolute_url(), sitemap)

    def test_sitemap_short_url_slug_and_links(self):
        own = job(self.unicef, "Child Protection Officer", 1)
        url = self.unicef.organization.get_absolute_url()
        self.assertEqual(url, f"/sources/{self.unicef.organization.pk}/unicef-u-bosni-i-hercegovini/")
        self.assertRedirects(self.client.get(f"/sources/{self.unicef.organization.pk}/?page=1"), url + "?page=1", status_code=301, fetch_redirect_response=False)
        self.assertEqual(self.client.get(url, {"page": 9}).status_code, 404)
        self.assertIn(url, self.client.get("/sitemap.xml").content.decode())
        self.assertIn("/en" + url, self.client.get("/sitemap.xml").content.decode())
        self.assertContains(self.client.get("/sources/"), f'href="{url}"')
        self.assertContains(self.client.get("/"), f'class="employer-link" href="{url}"')
        self.assertContains(self.client.get(own.get_absolute_url()), f'href="{url}"')
        self.assertEqual(self.client.get("/en" + url).status_code, 200)


class PublishedAtTests(TestCase):
    def test_set_once_when_a_job_becomes_public(self):
        item = job(source("Ambasada Japana"), "Driver", 1, status="review")
        self.assertIsNone(item.published_at)
        item.status = "published"
        item.save(update_fields=["status"])
        item.refresh_from_db()
        first = item.published_at
        self.assertIsNotNone(first)
        item.status = "closed"
        item.save()
        item.status = "published"
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.published_at, first)
