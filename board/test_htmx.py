from django.test import TestCase

from .models import Organization, Source
from .test_i18n import PLAIN_STATIC, make_job
from .test_requirements import UNDP


@PLAIN_STATIC
class HtmxJobListTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Ambasada Italije", kind="embassy")
        self.source = Source.objects.create(organization=organization, url="https://employer.test/jobs", adapter="generic", enabled=True, status="verified")
        make_job(self.source, "Project Coordinator", UNDP)

    def test_full_page_carries_the_partial_targets_and_script(self):
        response = self.client.get("/")
        self.assertContains(response, 'id="results"')
        self.assertContains(response, 'id="job-search"')
        self.assertContains(response, "htmx.min.js")
        self.assertContains(response, 'method="get"')
        self.assertContains(response, "Project Coordinator")
        self.assertIn("HX-Request", response["Vary"])

    def test_htmx_request_gets_the_results_partial(self):
        response = self.client.get("/", HTTP_HX_REQUEST="true")
        self.assertNotContains(response, "<html")
        self.assertContains(response, "Project Coordinator")
        self.assertContains(response, 'id="results-status"')
        self.assertNotContains(response, 'id="job-search"')
        self.assertIn("HX-Request", response["Vary"])

    def test_boosted_request_also_swaps_the_form(self):
        response = self.client.get("/", HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true")
        self.assertContains(response, 'id="job-search"')
        self.assertContains(response, 'hx-swap-oob="true"')

    def test_history_restore_gets_the_full_page(self):
        response = self.client.get("/", HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true")
        self.assertContains(response, "<html")

    def test_filtered_partial_shows_the_empty_state(self):
        response = self.client.get("/?q=zzzneposto", HTTP_HX_REQUEST="true")
        self.assertContains(response, '<span class="results-count">· 0')
        self.assertContains(response, "Trenutno nema oglasa koji odgovaraju pretrazi.")

    def test_full_page_has_one_status_element_and_no_oob_swap(self):
        response = self.client.get("/")
        self.assertEqual(response.content.decode().count('id="results-status"'), 1)
        self.assertNotContains(response, "hx-swap-oob")
