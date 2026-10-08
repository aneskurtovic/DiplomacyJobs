from django.test import TestCase

from .models import Organization, Report, Source
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

    def test_search_form_needs_no_eval(self):
        response = self.client.get("/")
        self.assertNotContains(response, "hx-on")
        self.assertNotContains(response, "[target.")
        self.assertContains(response, '"allowEval": false')
        self.assertContains(response, "search.js")

    def test_content_security_policy_forbids_foreign_and_inline_scripts(self):
        policy = self.client.get("/")["Content-Security-Policy"]
        script = next(part for part in policy.split("; ") if part.startswith("script-src"))
        self.assertRegex(script, r"^script-src 'self' 'nonce-[\w-]{16,}'$")
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertNotEqual(policy, self.client.get("/")["Content-Security-Policy"])

    def test_load_more_appends_the_next_page_without_the_page_links(self):
        for number in range(25):
            make_job(self.source, f"Assistant {number:02d}", f"{UNDP} {number}")
        first = self.client.get("/").content.decode()
        self.assertIn('class="button-secondary load-more" data-shown="20" href="?page=2"', first)
        self.assertIn('class="pagination"', first)
        more = self.client.get("/?page=2", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="pager")
        self.assertNotContains(more, 'id="job-search"')
        self.assertNotContains(more, 'class="pagination"')
        self.assertNotContains(more, "load-more")
        self.assertContains(more, "Prikazano 26 od 26")
        self.assertEqual(more.content.decode().count('class="job-card'), 6)
        self.assertIn("HX-Target", more["Vary"])


@PLAIN_STATIC
class HtmxReportTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Ambasada Italije", kind="embassy")
        source = Source.objects.create(organization=organization, url="https://employer.test/jobs", adapter="generic", enabled=True, status="verified")
        self.job = make_job(source, "Project Coordinator", UNDP)
        self.url = f"/jobs/{self.job.pk}/report/"

    def test_form_posts_in_place(self):
        self.assertContains(self.client.get(self.job.get_absolute_url()), f'hx-post="{self.url}"')

    def test_sent_report_answers_with_thanks_in_place(self):
        response = self.client.post(self.url, {"reason": "expired"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, "Prijava je zaprimljena")
        self.assertContains(response, f'href="{self.job.get_absolute_url()}"')
        self.assertEqual(Report.objects.count(), 1)

    def test_invalid_report_returns_the_form_with_errors(self):
        response = self.client.post(self.url, {"reason": "other"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(response, "<html")
        self.assertContains(response, "Opišite ukratko problem.")
        self.assertContains(response, 'class="report-form"')
        self.assertFalse(Report.objects.exists())

    def test_sent_site_report_links_back_to_its_page(self):
        response = self.client.post("/report/", {"reason": "site", "page": "/sources/"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, 'href="/sources/"')
