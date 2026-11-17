"""Job search markup on job pages, and indexing of filtered job lists."""
import json
import re
from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs
from xml.etree import ElementTree

from django.test import TestCase, override_settings
from django.utils import timezone, translation

from .test_related import STATIC, job, source


class Links(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.urls = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        if tag in ("a", "link"):
            self.urls.extend(value for key, value in attrs if key == "href")


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
        self.assertNotContains(response, 'name="robots" content="noindex')

    def test_filtered_list_is_indexable(self):
        job(self.undp, "Driver", 3)
        self.assertNotContains(self.client.get("/"), "noindex")
        response = self.client.get("/?city=Sarajevo")
        self.assertNotContains(response, 'name="robots" content="noindex')
        self.assertContains(response, '<link rel="canonical" href="https://example.org/">')
        self.assertNotContains(self.client.get("/?sort=deadline"), "noindex, follow")

    def test_public_archive_is_readable_and_in_both_language_sitemaps(self):
        archived = job(self.undp, "Archived officer", 90, status="closed", closed_reason="archive", published_at=timezone.now(), deadline=timezone.localdate() - timedelta(days=10))
        sitemap = self.client.get("/sitemap.xml")
        for prefix in ("", "/en"):
            url = prefix + archived.get_absolute_url()
            response = self.client.get(url)
            self.assertContains(response, archived.title)
            self.assertNotContains(response, "noindex")
            self.assertIsNone(posting(response))
            self.assertContains(sitemap, "https://example.org" + url)
        self.assertContains(self.client.get(self.undp.organization.get_absolute_url()), f'href="{archived.get_absolute_url()}"')

    def test_hidden_closed_jobs_stay_out_of_the_archive(self):
        for number, reason in enumerate(("manual", "duplicate", "deadline")):
            hidden = job(self.undp, "Hidden record", 100 + number, status="closed", closed_reason=reason)
            self.assertIsNone(hidden.published_at)
            self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 410)
            self.assertNotContains(self.client.get("/sitemap.xml"), "https://example.org" + hidden.get_absolute_url())
        for number, reason in enumerate(("manual", "duplicate")):
            rejected = job(self.undp, "Rejected public record", 110 + number, status="closed", closed_reason=reason, published_at=timezone.now())
            self.assertEqual(self.client.get(rejected.get_absolute_url()).status_code, 410)
            self.assertNotContains(self.client.get("/sitemap.xml"), "https://example.org" + rejected.get_absolute_url())

    def test_report_links_do_not_recursively_embed_report_pages(self):
        for prefix in ("", "/en"):
            url = prefix + "/report/?page=/report/?page%3D/en/jobs/17/example/"
            response = self.client.get(url)
            for link in Links(response.content.decode()).urls:
                parsed = urlsplit(link)
                if parsed.path.endswith("/report/"):
                    self.assertNotIn("page", parse_qs(parsed.query), link)
            self.assertEqual(response.context["page"], "")
            self.assertContains(response, 'name="page" value=""')

    def test_every_organization_is_indexable_even_without_jobs(self):
        response = self.client.get(self.undp.organization.get_absolute_url())
        self.assertNotContains(response, "noindex")
        self.assertContains(self.client.get("/sitemap.xml"), "https://example.org" + self.undp.organization.get_absolute_url())

    def test_every_sitemap_url_is_readable_and_indexable(self):
        job(self.undp, "Current officer", 120)
        job(self.undp, "Former officer", 121, status="closed", closed_reason="deadline", published_at=timezone.now())
        tree = ElementTree.fromstring(self.client.get("/sitemap.xml").content)
        for loc in tree.findall("{*}url/{*}loc"):
            with self.subTest(url=loc.text):
                response = self.client.get(urlsplit(loc.text).path)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "noindex")

    def test_later_pages_are_their_own_canonical(self):
        for number in range(21):
            job(self.undp, f"Officer {number}", 10 + number)
        self.assertContains(self.client.get("/?page=2"), '<link rel="canonical" href="https://example.org/?page=2">')

    def test_empty_filtered_result_offers_a_reset(self):
        response = self.client.get("/?q=nothing-matches")
        self.assertContains(response, "Poništi filtere")
