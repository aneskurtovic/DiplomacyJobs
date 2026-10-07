"""Job search markup on job pages, and indexing of filtered job lists."""
import json
import re
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone, translation

from .test_related import STATIC, job, source


def posting(response):
    found = re.search(r'<script type="application/ld\+json">(.*?)</script>', response.content.decode(), re.S)
    return json.loads(found.group(1)) if found else None


@override_settings(STORAGES=STATIC, PUBLIC_BASE_URL="https://example.org")
class SeoTests(TestCase):
    def setUp(self):
        translation.activate("bs")
        self.addCleanup(translation.deactivate)
        self.undp = source("UNDP u Bosni i Hercegovini", short_name="UNDP", website="https://undp.example")

    def test_current_job_has_job_posting(self):
        current = job(self.undp, "Project <Assistant>", 1, opportunity_type="paid_internship", education_level="bachelor", experience_years=2, eligibility="Samo državljani BiH <script>.")
        data = posting(self.client.get(current.get_absolute_url()))
        self.assertEqual((data["@type"], data["title"], data["employmentType"]), ("JobPosting", "Project <Assistant>", "INTERN"))
        self.assertEqual(data["hiringOrganization"], {"@type": "Organization", "name": "UNDP u Bosni i Hercegovini", "sameAs": "https://undp.example"})
        self.assertEqual(data["jobLocation"]["address"]["addressLocality"], "Sarajevo")
        self.assertTrue(data["validThrough"].startswith(str(current.deadline)))
        self.assertEqual(data["url"], "https://example.org" + current.get_absolute_url())
        self.assertEqual(data["experienceRequirements"]["monthsOfExperience"], 24)
        self.assertEqual(data["educationRequirements"]["credentialCategory"], "bachelor degree")
        self.assertIn("Samo državljani", data["description"])
        self.assertIn("BiH &lt;script&gt;.", data["description"])
        self.assertNotIn("</script>", data["description"])

    def test_expired_job_has_no_job_posting(self):
        expired = job(self.undp, "Driver", 2, deadline=timezone.localdate() - timedelta(days=1))
        response = self.client.get(expired.get_absolute_url())
        self.assertIsNone(posting(response))
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_filtered_list_is_not_indexed(self):
        job(self.undp, "Driver", 3)
        self.assertNotContains(self.client.get("/"), "noindex")
        response = self.client.get("/?city=Sarajevo")
        self.assertContains(response, '<meta name="robots" content="noindex, follow">')
        self.assertContains(response, '<link rel="canonical" href="https://example.org/">')
        self.assertContains(self.client.get("/?sort=deadline"), "noindex, follow")

    def test_later_pages_are_their_own_canonical(self):
        for number in range(21):
            job(self.undp, f"Officer {number}", 10 + number)
        self.assertContains(self.client.get("/?page=2"), '<link rel="canonical" href="https://example.org/?page=2">')

    def test_empty_filtered_result_offers_a_reset(self):
        response = self.client.get("/?q=nothing-matches")
        self.assertContains(response, "Poništi filtere")
