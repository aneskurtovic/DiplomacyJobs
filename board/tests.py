import json
from datetime import date
from unittest import skipUnless
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from .ingest import discover_links, eeas_page_links, fetch, make_candidate, open_client, parse_deadline, unct_page_links
from .models import Job, Organization, Source

LISTING = """
<div class="card node--type-vacancy"><h3 class="card-title"><a href="/delegations/bosnia-and-herzegovina/head-communications_en">Head of Communications and Spokesperson (IS 2026/02)</a></h3>
  <div class="deadline">Deadline 28.10.2026</div></div>
<div class="card node--type-vacancy"><h3 class="card-title"><a href="/delegations/bosnia-and-herzegovina/political-officer_en">Political Officer</a></h3>
  <div class="deadline">Deadline 12.10.2025</div></div>
<div class="card node--type-vacancy"><h3 class="card-title"><a href="https://example.com/fake_en">Spoofed</a></h3></div>
"""

DETAIL = """
<nav>Vacancies in Kosovo and Serbia</nav>
<div class="content-header"><h1>Head of Communications and Spokesperson (IS 2026/02)</h1>
  <div class="node__meta"><div> 01.10.2026 </div> New opportunity</div></div>
<article class="node node--type-vacancy node--view-mode-full">
  Location: Sarajevo, Bosnia and Herzegovina. Deadline 28.10.2026.
</article>
"""


class SourceBoundaryTests(TestCase):
    def test_trusted_host_requires_a_domain_boundary(self):
        from .ingest import trusted_host
        for host in ("ohr.int", "www.ohr.int", "jobs.www.ohr.int"):
            with self.subTest(host=host):
                self.assertTrue(trusted_host(host, "ohr.int"))
        for host in ("evilohr.int", "ohr.int.evil.example", "", "ohr.int@evil.example"):
            with self.subTest(host=host):
                self.assertFalse(trusted_host(host, "ohr.int"))

    def test_fetch_rejects_a_redirect_to_a_lookalike_host(self):
        from unittest.mock import Mock
        response = httpx.Response(200, text="<h1>Vacancy</h1>", headers={"content-type": "text/html"}, request=httpx.Request("GET", "https://evilohr.int/jobs"))
        with self.assertRaisesMessage(ValueError, "Unexpected redirect host"):
            fetch(Mock(get=Mock(return_value=response)), "https://ohr.int/jobs")

    def test_only_clearly_dated_archives_are_skipped(self):
        from .ingest import listing_link_in_scope
        cases = {
            "https://emb.example/2025/09/driver": False,
            "https://emb.example/2027/1/driver": False,
            "https://emb.example/2026/10/driver": True,
            "https://emb.example/jobs/driver?year=2025": True,
            "https://emb.example/jobs/2025-2026-driver": True,
            "https://emb.example/2025/13/driver": True,
            "https://emb.example/jobs/driver": True,
        }
        for url, allowed in cases.items():
            with self.subTest(url=url):
                self.assertEqual(listing_link_in_scope(url, "Vacancy 2026"), allowed)


class EeasAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="EU Delegation", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="eeas", url="https://www.eeas.europa.eu/eeas/vacancies_en?f%5B0%5D=vacancy_site%3ABosnia%20and%20Herzegovina")

    def test_listing_keeps_2026_cards_regardless_of_title_words(self):
        links = eeas_page_links(self.source, BeautifulSoup(LISTING, "html.parser"))
        self.assertEqual(links, [("https://www.eeas.europa.eu/delegations/bosnia-and-herzegovina/head-communications_en", "Head of Communications and Spokesperson (IS 2026/02)")])

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_detail_uses_article_text_and_meta_publication_date(self, _):
        soup = BeautifulSoup(DETAIL, "html.parser")
        candidate = make_candidate(self.source, "https://www.eeas.europa.eu/x", "listing title", soup.get_text(" ", strip=True), soup)
        self.assertEqual(candidate.source_published_at, date(2026, 10, 1))
        self.assertEqual(candidate.deadline, date(2026, 10, 28))
        self.assertEqual(candidate.city, "Sarajevo")
        self.assertNotIn("Kosovo", candidate.text)
        self.assertTrue(candidate.eligible)
        self.assertTrue(candidate.year_proven)

    def test_detail_without_vacancy_article_fails(self):
        soup = BeautifulSoup("<h1>Not found</h1>", "html.parser")
        with self.assertRaises(ValueError):
            make_candidate(self.source, "https://www.eeas.europa.eu/x", "t", "Not found", soup)


UN_CARD = """
<div class="view-jobs"><div class="view-content">
<article class="node node--type-job-vacancy node--view-mode-teaser"><div class="node__content"><div class="border">
  <div>17 April 2026</div>
  <div class="text-2xl"><a href="https://jobs.unicef.org/en-us/job/591463">Programme Associate, G-6, Fixed Term Position, Sarajevo, Bosnia and Herzegovina, #134897 (1 position)</a></div>
  <div class="flex"><div>Closing date</div><div>25 April 2026</div></div>
  <div>UNICEF: United Nations Children's Fund</div>
</div></div></article>
<article class="node node--type-job-vacancy node--view-mode-teaser"><div class="node__content"><div class="border">
  <div>02 December 2025</div>
  <div class="text-2xl"><a href="https://jobs.undp.org/old">Old Analyst, Sarajevo</a></div>
  <div class="flex"><div>Closing date</div><div>20 December 2025</div></div>
  <div>UNDP</div>
</div></div></article>
</div></div>
"""


class UnctAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="UN BiH", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="unct", url="https://bosniaherzegovina.un.org/en/jobs", adapter_config={"allow_empty": True})

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 4, 20))
    def test_card_is_the_evidence(self, _):
        evidence = {}
        links = unct_page_links(self.source, BeautifulSoup(UN_CARD, "html.parser"), evidence)
        self.assertEqual([url for url, _ in links], ["https://jobs.unicef.org/en-us/job/591463"])
        url, title = links[0]
        candidate = make_candidate(self.source, url, title, evidence[url], None)
        self.assertEqual(candidate.source_published_at, date(2026, 4, 17))
        self.assertEqual(candidate.deadline, date(2026, 4, 25))
        self.assertEqual(candidate.city, "Sarajevo")
        self.assertTrue(candidate.eligible)
        self.assertTrue(candidate.year_proven)

    def test_card_of_an_agency_with_its_own_enabled_source_is_skipped(self):
        agency = Source.objects.create(organization=self.source.organization, adapter="generic", url="https://jobs.unicef.org/en-us/search/", enabled=True)
        self.assertEqual(unct_page_links(self.source, BeautifulSoup(UN_CARD, "html.parser"), {}), [])
        agency.enabled = False
        agency.save()
        self.assertEqual(len(unct_page_links(self.source, BeautifulSoup(UN_CARD, "html.parser"), {})), 1)

    def test_pagination_stops_when_a_page_repeats(self):
        soup = BeautifulSoup(UN_CARD, "html.parser")
        with patch("board.ingest.fetch", return_value=("", BeautifulSoup(UN_CARD, "html.parser"))) as fetch:
            links = discover_links(None, self.source, soup, {})
        self.assertEqual(len(links), 1)
        self.assertEqual(fetch.call_count, 1)

    def test_empty_view_is_allowed_but_missing_view_fails(self):
        self.assertEqual(discover_links(None, self.source, BeautifulSoup('<div class="view-jobs"></div>', "html.parser"), {}), [])
        with self.assertRaises(ValueError):
            discover_links(None, self.source, BeautifulSoup("<main>Maintenance</main>", "html.parser"), {})


OHR_LISTING = """
<main><h4><u>National (open to B&amp;H citizens only)</u></h4><p><i>Sorry, no active vacancy available.</i></p>
<div class="big-space"></div>
<h4><u>International (open to citizens of any country, including B&amp;H citizens)</u></h4>
<table id="vacancy-table"><thead><tr><th>Vacancy</th><th>Duty Station</th><th>Closing Date</th></tr></thead>
<tbody><article><tr><td><a href="https://www.ohr.int/vacancy-legal-adviser/">Legal Adviser</a></td><td>Sarajevo</td><td>11/05/2026</td></tr></article></tbody></table>
</main>
"""

OHR_DETAIL = """
<main><article class="post"><header class="entry-header"><span class="date-publish">10/20/2026</span>
<h1 class="entry-title">Legal Adviser</h1></header>
<div>The Office of the High Representative in Bosnia and Herzegovina seeks a Legal Adviser.</div></article></main>
<aside>Press release about Serbia</aside>
"""


class OhrAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="OHR", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="ohr", url="https://www.ohr.int/vacancies/", adapter_config={"allow_empty": True})

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 21))
    def test_table_row_and_post_make_a_dated_candidate(self, _):
        evidence = {}
        links = discover_links(None, self.source, BeautifulSoup(OHR_LISTING, "html.parser"), evidence)
        self.assertEqual(links, [("https://www.ohr.int/vacancy-legal-adviser", "Legal Adviser")])
        url, title = links[0]
        soup = BeautifulSoup(OHR_DETAIL, "html.parser")
        candidate = make_candidate(self.source, url, title, soup.get_text(" ", strip=True), soup, evidence[url])
        self.assertEqual(candidate.deadline, date(2026, 11, 5))
        self.assertEqual(candidate.source_published_at, date(2026, 10, 20))
        self.assertNotIn("Serbia", candidate.text)
        self.assertTrue(candidate.eligible)
        self.assertTrue(candidate.year_proven)

    def test_section_without_table_or_empty_note_fails(self):
        with self.assertRaises(ValueError):
            discover_links(None, self.source, BeautifulSoup("<main><h4>Consultancy</h4><p>Coming soon</p></main>", "html.parser"), {})


EUFOR_LISTING = """
<div class="category-desc"><!-- <p>Thank you for your interest, but at this time, we do not have any vacancies available</p> -->
<h4>Local Civilian Hires (LCH)</h4>
<p><a href="/images/stories/vacancy/purchasingAdmin.pdf"><strong>Purchasing Administrator</strong></a><br/>Post no. CL FIN 0056<br/>Grade: LCH-6<br/>
Closing for application: 29 October 2026<br/><a href="/images/stories/vacancy/purchasingAdmin.pdf"><strong>Job description...</strong></a></p>
</div>
"""


class PdfDateTests(TestCase):
    def test_opted_in_pdf_source_takes_the_file_date_as_publication(self):
        from .ingest import ingest_source
        organization = Organization.objects.create(name="EUFOR", kind="international")
        source = Source.objects.create(organization=organization, adapter="generic", url="https://eufor.example/jobs", status="verified", enabled=True, adapter_config={"allow_empty": True, "link_selector": "a", "pdf_date_as_published": True})
        listing = BeautifulSoup('<a href="/vacancy/admin.pdf">Vacancy: Purchasing Administrator</a>', "html.parser")
        def fake_fetch(client, url):
            if url == source.url:
                return listing.get_text(), listing
            return "Vacancy: Purchasing Administrator. Duty location: Sarajevo. Closing for application: 29 October 2026.", None
        with patch("board.ingest.fetch", side_effect=fake_fetch), patch("board.ingest.file_date", return_value=date(2026, 9, 29)), patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2)):
            self.assertTrue(ingest_source(source.pk).success)
        job = source.jobs.get()
        self.assertEqual((job.status, job.source_published_at, job.deadline), ("published", date(2026, 9, 29), date(2026, 10, 29)))


class EuforAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="EUFOR", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="eufor", url="https://www.euforbih.org/index.php/vacancies-a")

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_pdf_vacancy_is_deadline_only_lead(self, _):
        evidence = {}
        links = discover_links(None, self.source, BeautifulSoup(EUFOR_LISTING, "html.parser"), evidence)
        self.assertEqual(links, [("https://www.euforbih.org/images/stories/vacancy/purchasingAdmin.pdf", "Purchasing Administrator")])
        url, title = links[0]
        candidate = make_candidate(self.source, url, title, "Job title: PURCHASING ADMINISTRATOR Duty location: Sarajevo, Butmir", None, evidence[url])
        self.assertEqual(candidate.deadline, date(2026, 10, 29))
        self.assertTrue(candidate.eligible)
        self.assertTrue(candidate.in_scope_year)
        self.assertFalse(candidate.year_proven)

    def test_empty_block_without_no_vacancies_note_fails(self):
        with self.assertRaises(ValueError):
            discover_links(None, self.source, BeautifulSoup('<div class="category-desc"><h4>Local Civilian Hires</h4></div>', "html.parser"), {})
        self.assertEqual(discover_links(None, self.source, BeautifulSoup('<div class="category-desc"><p>At this time, we do not have any vacancies available</p></div>', "html.parser"), {}), [])


class FetchTests(TestCase):
    def test_empty_challenge_response_is_a_failure(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(202, content=b"", headers={"content-type": "text/html"})))
        with self.assertRaises(ValueError):
            fetch(client, "https://jobs.unicef.org/en-us/search/")


def ebrd_row(title, location, href):
    return f'<tr class="data-row"><td class="colTitle"><a class="jobTitle-link" href="{href}">{title}</a></td><td class="colLocation"><span class="jobLocation">{location}</span></td></tr>'


EBRD_DETAIL = """
<h1>Associate Banker</h1><span id="job-date">Posting Date: 21 Sept 2026</span><meta itemprop="datePosted" content="Mon Sep 21 00:00:00 UTC 2026">
<span class="jobdescription">Requisition ID 37100 Office Country Bosnia and Herzegovina Office City Sarajevo Contract Type Fixed Term Posting End Date 05/10/2026 Purpose of Job: covers the Western Balkans.</span>
"""


class RetryTests(TestCase):
    def test_dropped_connection_retried_once(self):
        calls = []
        def flaky(request):
            calls.append(request.url)
            if len(calls) == 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return httpx.Response(200, text="<p>Vacancy</p>", headers={"content-type": "text/html"})
        with httpx.Client(transport=httpx.MockTransport(flaky)) as client:
            self.assertEqual(fetch(client, "https://a.example/jobs")[0], "Vacancy")
        self.assertEqual(len(calls), 2)


class EbrdAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="EBRD", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="ebrd", url="https://jobs.ebrd.com/search/?q=&locationsearch=Sarajevo")

    def test_fallback_rows_from_other_countries_are_dropped(self):
        html = '<div id="searchresults"><table>' + ebrd_row("Principal Banker", "Lagos, NG", "/job/Lagos-Principal-Banker/1/") + ebrd_row("Associate Banker", "Sarajevo, BA", "/job/Sarajevo-Associate-Banker/2/") + '</table></div><span class="paginationLabel">Results 1 – 2 of 2</span>'
        links = discover_links(None, self.source, BeautifulSoup(html, "html.parser"), {})
        self.assertEqual(links, [("https://jobs.ebrd.com/job/Sarajevo-Associate-Banker/2", "Associate Banker")])

    def test_unseen_bih_pages_fail(self):
        html = '<div id="searchresults"><table>' + ebrd_row("Associate Banker", "Sarajevo, BA", "/job/a/2/") + '</table></div><span class="paginationLabel">Results 1 – 1 of 30</span>'
        with self.assertRaises(ValueError):
            discover_links(None, self.source, BeautifulSoup(html, "html.parser"), {})

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 9, 25))
    def test_detail_uses_structured_posting_date_and_end_date(self, _):
        soup = BeautifulSoup(EBRD_DETAIL, "html.parser")
        candidate = make_candidate(self.source, "https://jobs.ebrd.com/job/a/2", "Associate Banker", soup.get_text(" ", strip=True), soup)
        self.assertEqual(candidate.source_published_at, date(2026, 9, 21))
        self.assertEqual(candidate.deadline, date(2026, 10, 5))
        self.assertEqual(candidate.city, "Sarajevo")
        self.assertTrue(candidate.eligible)
        self.assertTrue(candidate.year_proven)


def rcc_card(number, title, published, deadline):
    return f"""<div class="page doc-item"><p class="title lh-sm">{number}  Terms of Reference {title}</p>
<p class="bg-light"><strong>Published:</strong><span>{published}</span><strong>Deadline:</strong><span>{deadline}</span></p>
<p>RCC Secretariat is looking for the {title}</p>
<p><a href="https://www.rcc.int/vacancy_apps/blank/{number[:3]}">Apply</a></p></div>"""


class RccAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="RCC", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="rcc", url="https://www.rcc.int/vacancies")

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 1, 20))
    def test_secretariat_card_publishes_and_brussels_card_needs_review(self, _):
        html = rcc_card("001-026", "Head of Political Department", "17 JANUARY 2026", "17 FEBRUARY 2026") + rcc_card("003-026", "Head of Liaison Office in Brussels", "17 JANUARY 2026", "17 FEBRUARY 2026")
        evidence = {}
        links = discover_links(None, self.source, BeautifulSoup(html, "html.parser"), evidence)
        self.assertEqual([title for _, title in links], ["Head of Political Department", "Head of Liaison Office in Brussels"])
        sarajevo, brussels = [make_candidate(self.source, url, title, evidence[url], None) for url, title in links]
        self.assertEqual(sarajevo.source_published_at, date(2026, 1, 17))
        self.assertEqual(sarajevo.deadline, date(2026, 2, 17))
        self.assertTrue(sarajevo.eligible and sarajevo.year_proven)
        self.assertFalse(brussels.eligible)

    def test_page_without_cards_or_note_fails(self):
        self.assertEqual(discover_links(None, self.source, BeautifulSoup("<p>There are currently no open vacancies.</p>", "html.parser"), {}), [])
        with self.assertRaises(ValueError):
            discover_links(None, self.source, BeautifulSoup("<p>Under maintenance</p>", "html.parser"), {})


ERA_ROW = '<a href="/dos-era/vacancy/viewVacancyDetail.hms?_ref=abc123&returnToSearch=true&jnum={jnum}&orgId=121">{title}</a>'


class EraAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="US Embassy", kind="embassy")
        self.source = Source.objects.create(organization=organization, adapter="era", url="https://erajobs.state.gov/dos-era/bih/vacancysearch/searchVacancies.hms")

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_session_token_dropped_and_open_period_parsed(self, _):
        html = "2 records found, showing 1 - 2 of 2" + ERA_ROW.format(jnum=77122, title="Senior Guard") + ERA_ROW.format(jnum=77608, title="Electrical Engineer Supervisor")
        links = discover_links(None, self.source, BeautifulSoup(html, "html.parser"))
        self.assertEqual(links[1], ("https://erajobs.state.gov/dos-era/vacancy/viewVacancyDetail.hms?jnum=77608&orgId=121", "Electrical Engineer Supervisor"))
        detail = "<h1>U.S. Department Of State</h1>Open Period: 09/25/2026 - 10/08/2026 Duty Location(s): 1 Vacancy in Sarajevo, BK"
        soup = BeautifulSoup(detail, "html.parser")
        candidate = make_candidate(self.source, links[1][0], links[1][1], soup.get_text(" ", strip=True), soup)
        self.assertEqual(candidate.title, "Electrical Engineer Supervisor")
        self.assertEqual((candidate.source_published_at, candidate.deadline), (date(2026, 9, 25), date(2026, 10, 8)))
        self.assertTrue(candidate.eligible and candidate.year_proven)

    def test_unseen_results_fail(self):
        with self.assertRaises(ValueError):
            discover_links(None, self.source, BeautifulSoup("12 records found, showing 1 - 10 of 12" + ERA_ROW.format(jnum=1, title="Driver"), "html.parser"))
        self.assertEqual(discover_links(None, self.source, BeautifulSoup("0 records found", "html.parser")), [])


class JapanAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Japan Embassy", kind="embassy")
        self.source = Source.objects.create(organization=organization, adapter="japan", url="https://www.bosnia.emb-japan.go.jp/itprtop_bs/index.html", adapter_config={"path_contains": "/itpr", "impersonate": True})

    def candidate(self, title, body):
        soup = BeautifulSoup(f"<h1>{title}</h1><p>2026/8/4</p>{body}", "html.parser")
        return make_candidate(self.source, "https://www.bosnia.emb-japan.go.jp/itpr_ja/11_000001_01094.html", title, soup.get_text(" ", strip=True), soup)

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 8, 10))
    def test_slash_date_is_publication_and_comma_deadline_parses(self, _):
        candidate = self.candidate("Embassy of Japan in BiH Job Recruitment", "Assistant. Working location: Sarajevo. THE DEADLINE FOR APPLICATIONS IS AUGUST 25,2026.")
        self.assertEqual((candidate.source_published_at, candidate.deadline), (date(2026, 8, 4), date(2026, 8, 25)))
        self.assertTrue(candidate.eligible and candidate.year_proven)

    def test_scholarship_is_excluded(self):
        self.assertTrue(self.candidate("Konkurs za stipendije Vlade Japana (MEXT)", "Sarajevo").excluded)

    def test_impersonation_is_opt_in(self):
        with open_client(self.source) as client:
            self.assertNotIsInstance(client, httpx.Client)
        self.source.adapter_config = {}
        with open_client(self.source) as client:
            self.assertIsInstance(client, httpx.Client)


class DateParsingTests(TestCase):
    def test_deadline_formats(self):
        for text, expected in [("najkasnije do 17. septembra 2026.", date(2026, 9, 17)), ("Deadline: August 25, 2026", date(2026, 8, 25)), ("deadline AUGUST 25,2026", date(2026, 8, 25)), ("Closing date 2026-10-15", date(2026, 10, 15))]:
            self.assertEqual(parse_deadline(text), expected, text)

    def test_more_deadline_shapes(self):
        cases = [
            ("Široki Brijeg, 01.03.2026. Deadline: 15.10.2026", date(2026, 10, 15)),
            ("Closing date: Sept 30, 2026", date(2026, 9, 30)),
            ("Rok za prijavu: 15. 10. 2026.", date(2026, 10, 15)),
            ("Deadline: 15th October 2026", date(2026, 10, 15)),
            ("Deadline: 15 October, 2026", date(2026, 10, 15)),
            ("Deadline 2026/10/15", date(2026, 10, 15)),
            ("Deadline to apply 15-Oct-2026", date(2026, 10, 15)),
            ("Rok za prijavu je 15. listopada 2026.", date(2026, 10, 15)),
            ("Deadline: October 15 2026 (extended to 30 October 2026)", date(2026, 10, 30)),
            ("Deadline: 99.99.2026, corrected deadline: 20.10.2026", date(2026, 10, 20)),
        ]
        for text, expected in cases:
            self.assertEqual(parse_deadline(text), expected, text)

    def test_italian_and_nominative_months(self):
        from .ingest import parse_published
        self.assertEqual(parse_published("Data pubblicazione: 28 Aprile 2026"), date(2026, 4, 28))
        self.assertEqual(parse_deadline("Rok za prijavu: 5. oktobar 2026."), date(2026, 10, 5))


def oracle_api(request):
    if "recruitingCEJobRequisitions" in str(request.url):
        rows = [{"Id": "37232", "Title": "Joint Project Coordinator", "PrimaryLocationCountry": "BA"}, {"Id": "20334", "Title": "Diaspora Experts", "PrimaryLocationCountry": "AL"}]
        return httpx.Response(200, json={"items": [{"TotalJobsCount": 2, "requisitionList": rows}]})
    assert "37232" in str(request.url), request.url
    detail = {"Title": "Joint Project Coordinator", "PrimaryLocation": "Sarajevo, Bosnia and Herzegovina", "ExternalPostedStartDate": "2026-09-30T14:26:07+00:00", "ExternalPostedEndDate": "2026-10-08T03:59:00+00:00", "ExternalDescriptionStr": "<p>Delivers work by deadline.</p>"}
    return httpx.Response(200, json={"items": [detail]})


class OracleAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="UN", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="oracle", url="https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions")

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_bih_requisition_kept_with_office_closing_day(self, _):
        evidence = {}
        with httpx.Client(transport=httpx.MockTransport(oracle_api)) as client:
            links = discover_links(client, self.source, None, evidence)
        url = "https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/37232"
        self.assertEqual(links, [(url, "Joint Project Coordinator")])
        candidate = make_candidate(self.source, url, links[0][1], evidence[url], None)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 9, 30), date(2026, 10, 7), "Sarajevo"))
        self.assertTrue(candidate.eligible and candidate.year_proven)

    def test_truncated_search_fails(self):
        truncated = lambda request: httpx.Response(200, json={"items": [{"TotalJobsCount": 150, "requisitionList": []}]})
        with httpx.Client(transport=httpx.MockTransport(truncated)) as client, self.assertRaises(ValueError):
            discover_links(client, self.source, None, {})


def workday_api(request):
    if request.url.path.endswith("/jobs"):
        body = json.loads(request.content)
        countries = {"facetParameter": "locationMainGroup", "values": [{"facetParameter": "locationCountry", "values": [{"descriptor": "Bosnia and Herzegovina", "id": "ba1"}, {"descriptor": "Hungary", "id": "hu1"}]}]}
        if not body["appliedFacets"]:
            return httpx.Response(200, json={"total": 14, "jobPostings": [], "facets": [countries]})
        assert body["appliedFacets"] == {"locationCountry": ["ba1"]}
        return httpx.Response(200, json={"total": 1, "jobPostings": [{"title": "Protection Associate", "externalPath": "/job/Sarajevo/Protection-Associate_JR1"}], "facets": [countries]})
    info = {"title": "Protection Associate", "location": "Sarajevo", "startDate": "2026-10-01", "endDate": "2026-10-16", "jobDescription": "<p>Deadline for Applications October 15, 2026</p>", "externalUrl": "https://unhcr.wd3.myworkdayjobs.com/External/job/Sarajevo/Protection-Associate_JR1", "jobRequisitionLocation": {"country": {"descriptor": "Bosnia and Herzegovina", "alpha2Code": "BA"}}}
    return httpx.Response(200, json={"jobPostingInfo": info})


class WorkdayAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="UN", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="workday", url="https://unhcr.wd3.myworkdayjobs.com/External")

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_country_facet_filters_and_stated_deadline_wins(self, _):
        evidence = {}
        with httpx.Client(transport=httpx.MockTransport(workday_api)) as client:
            links = discover_links(client, self.source, None, evidence)
        self.assertEqual(len(links), 1)
        candidate = make_candidate(self.source, links[0][0], links[0][1], evidence[links[0][0]], None)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 10, 1), date(2026, 10, 15), "Sarajevo"))
        self.assertTrue(candidate.eligible and candidate.year_proven)

    def test_no_bih_country_means_empty(self):
        no_bih = lambda request: httpx.Response(200, json={"total": 1, "jobPostings": [], "facets": [{"facetParameter": "locationCountry", "values": [{"descriptor": "Hungary", "id": "hu1"}]}]})
        with httpx.Client(transport=httpx.MockTransport(no_bih)) as client:
            self.assertEqual(discover_links(client, self.source, None, {}), [])

    def test_location_facet_used_when_site_has_no_country_facet(self):
        def imf(request):
            if not request.url.path.endswith("/jobs"):
                return workday_api(request)
            places = {"facetParameter": "locationMainGroup", "values": [{"facetParameter": "locations", "values": [{"descriptor": "Gabon", "id": "ga1"}, {"descriptor": "Bosnia and Herzegovina, Sarajevo", "id": "sa1"}]}]}
            if json.loads(request.content)["appliedFacets"]:
                assert json.loads(request.content)["appliedFacets"] == {"locations": ["sa1"]}
                return httpx.Response(200, json={"total": 1, "jobPostings": [{"title": "Office Manager", "externalPath": "/job/Sarajevo/Protection-Associate_JR1"}]})
            return httpx.Response(200, json={"total": 15, "jobPostings": [], "facets": [places]})
        with httpx.Client(transport=httpx.MockTransport(imf)) as client:
            self.assertEqual(len(discover_links(client, self.source, None, {})), 1)


class OpportunityTypeTests(TestCase):
    def test_title_decides_type(self):
        from .ingest import opportunity_type
        for title, expected in [("Family Law and Legal Reform Expert, National Consultant,NOC, Sarajevo, BIH", "consultancy"), ("Project Associate [Open to internal and external applicants]", "employment"), ("PSP Fundraising Intern", "paid_internship"), ("Plaćena praksa u Ambasadi", "paid_internship"), ("Senior Guard", "employment")]:
            self.assertEqual(opportunity_type(title), expected, title)


def coe_card(number, title, station):
    return f'<article class="article article--result"><h3><a href="https://talents.coe.int/en_GB/careersmarketplace/JobDetail/{title.replace(" ", "-")}/{number}">{title}</a></h3><span class="list-item-dutyStation">{station}</span></article>'


class CoeAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="CoE", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="avature", url="https://talents.coe.int/en_GB/careersmarketplace/SearchJobs")

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_pages_followed_and_bih_station_kept(self, _):
        second = BeautifulSoup("2 results" + coe_card(1600, "Project Officer", "Sarajevo"), "html.parser")
        with patch("board.ingest.fetch", return_value=("", second)) as fetch_page:
            links = discover_links(None, self.source, BeautifulSoup("2 results" + coe_card(1565, "Head of Department", "Strasbourg"), "html.parser"))
        self.assertIn("jobOffset=1", fetch_page.call_args.args[1])
        self.assertEqual(links, [("https://talents.coe.int/en_GB/careersmarketplace/JobDetail/Project-Officer/1600", "Project Officer")])
        field = '<div class="article__content__view__field"><div class="article__content__view__field__label">{}</div><div class="article__content__view__field__value">{}</div></div>'
        detail = BeautifulSoup("".join(field.format(*pair) for pair in [("Vacancy number", "1600/2026"), ("Posted date", "22-Sep-2026"), ("Deadline to apply", "06-Oct-2026"), ("Duty station", "Sarajevo")]), "html.parser")
        candidate = make_candidate(self.source, links[0][0], links[0][1], detail.get_text(" ", strip=True), detail)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 9, 22), date(2026, 10, 6), "Sarajevo"))
        self.assertTrue(candidate.eligible and candidate.year_proven)

    def test_short_result_set_fails(self):
        with patch("board.ingest.fetch", return_value=("", BeautifulSoup("9 results", "html.parser"))), self.assertRaises(ValueError):
            discover_links(None, self.source, BeautifulSoup("9 results" + coe_card(1, "Officer", "Strasbourg"), "html.parser"))

    def test_ignored_offset_fails(self):
        first = BeautifulSoup("2 results" + coe_card(1565, "Head of Department", "Strasbourg"), "html.parser")
        with patch("board.ingest.fetch", return_value=("", first)), self.assertRaisesRegex(ValueError, "repeat"):
            discover_links(None, self.source, first)


class ImportRegistryTests(TestCase):
    def run_registry(self, registry):
        import io
        import tempfile
        from pathlib import Path
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            call_command("import_registry", str(path), stdout=io.StringIO())

    def test_nulls_rename_and_config_updates(self):
        live = Source.objects.create(organization=Organization.objects.create(name="Old name", kind="embassy"), url="https://x.example/jobs", adapter="generic", enabled=True, adapter_config={"link_selector": "a"})
        Source.objects.create(organization=live.organization, url="https://x.example/other", adapter="none", enabled=False)
        same = Source.objects.create(organization=live.organization, url="https://x.example/same", adapter="generic", enabled=True)
        self.run_registry([{"name": "New name", "previous_name": "Old name", "kind": "embassy", "city": None, "sources": [
            {"url": "https://x.example/jobs", "adapter": "osce", "adapter_config": {"link_selector": "main a", "empty_text": "No vacancies"}},
            {"url": "https://x.example/other", "adapter": "generic", "adapter_config": {"allow_empty": True}},
            {"url": "https://x.example/same", "adapter": "generic", "adapter_config": {"allow_empty": True}}]}])
        self.assertEqual(list(Organization.objects.values_list("name", "city")), [("New name", "")])
        live.refresh_from_db()
        # An enabled source keeps its parser and that parser's settings; a disabled or same-parser source takes both.
        self.assertEqual((live.adapter, live.adapter_config, live.enabled), ("generic", {"link_selector": "a"}, True))
        same.refresh_from_db()
        self.assertEqual(same.adapter_config, {"allow_empty": True})
        self.assertEqual(Source.objects.get(url="https://x.example/other").adapter, "generic")

    def test_recruitment_audit_import_is_repeatable_and_preserves_presence_date(self):
        item = {"name": "Audited", "kind": "embassy", "verified_at": "2026-09-01", "recruitment_status": "integration", "recruitment_checked_at": "2026-10-03", "recruitment_evidence_url": "https://a.example/jobs", "recruitment_notes": "Needs a country filter", "sources": [{"url": "https://a.example/jobs", "adapter": "none", "status": "unsupported", "enabled": False}]}
        self.run_registry([item])
        self.run_registry([item])
        org = Organization.objects.get(name="Audited")
        self.assertEqual((org.verified_at, org.recruitment_checked_at), (date(2026, 9, 1), date(2026, 10, 3)))
        self.assertEqual((Source.objects.count(), Job.objects.count()), (1, 0))
        self.assertFalse(org.sources.get().enabled)
        self.assertIsNone(org.sources.get().last_success_at)
        self.run_registry([{"name": "Audited", "kind": "embassy"}])
        org.refresh_from_db()
        self.assertEqual(org.recruitment_status, "integration")

    def test_incomplete_recruitment_audit_rolls_back_import(self):
        from django.core.management.base import CommandError
        with self.assertRaisesRegex(CommandError, "recruitment audit"):
            self.run_registry([{"name": "First", "kind": "embassy"}, {"name": "Incomplete", "kind": "embassy", "recruitment_status": "not_found", "recruitment_checked_at": "2026-10-03"}])
        self.assertFalse(Organization.objects.exists())

    def test_source_moved_to_another_organization_is_not_duplicated(self):
        import io
        import tempfile
        from pathlib import Path
        from django.core.management import call_command
        old = Organization.objects.create(name="UN", kind="international")
        Source.objects.create(organization=old, url="https://example.org/jobs", adapter="oracle", status="verified", enabled=True)
        registry = [{"name": "UNDP", "kind": "international", "sources": [{"url": "https://example.org/jobs", "adapter": "none", "enabled": False, "notes": "moved"}]}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            call_command("import_registry", str(path), stdout=io.StringIO())
        source = Source.objects.get(url="https://example.org/jobs")
        self.assertEqual((source.organization.name, source.notes, source.adapter, source.enabled), ("UNDP", "moved", "oracle", True))


OSCE_ROW = '<div class="job_list_row"><a class="job_link" href="https://vacancies.osce.org/jobs/chief-general-services-s3-4991">Chief, General Services (S3)</a><span class="location">BAH - OSCE Mission to Bosnia and Herzegovina, Sarajevo</span></div>'


class OsceAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="OSCE", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="osce", url="https://vacancies.osce.org/jobs/search/?location_ids=19")

    def test_result_count_must_match_rows(self):
        self.assertEqual(len(discover_links(None, self.source, BeautifulSoup("1 result" + OSCE_ROW, "html.parser"))), 1)
        self.assertEqual(discover_links(None, self.source, BeautifulSoup("0 results", "html.parser")), [])
        with self.assertRaises(ValueError):
            discover_links(None, self.source, BeautifulSoup("11 results" + OSCE_ROW, "html.parser"))


class IngestRulesTests(TestCase):
    """Publish/close rules of ingest_source against a generic listing, with fetch patched."""

    def setUp(self):
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        self.source = Source.objects.create(organization=organization, adapter="generic", url="https://emb.example/jobs", status="verified", enabled=True, adapter_config={"allow_empty": True})
        self.pages = {}
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 30.10.2026."))

    def listing(self, *jobs):
        self.pages = {self.source.url: "".join(f'<a href="/jobs/{slug}">{title}</a>' for slug, title, _ in jobs)}
        for slug, title, body in jobs:
            self.pages[f"https://emb.example/jobs/{slug}"] = f"<h1>{title}</h1><p>Location: Sarajevo. {body}</p>"

    def fake_fetch(self, client, url):
        if url not in self.pages:
            raise ValueError(f"Unusable response: {url}")
        soup = BeautifulSoup(self.pages[url], "html.parser")
        return soup.get_text(" ", strip=True), soup

    def run_ingest(self):
        from .ingest import ingest_source
        with patch("board.ingest.fetch", side_effect=self.fake_fetch), patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2)):
            return ingest_source(self.source.pk)

    def test_partial_listing_closes_deleted_known_page_without_failing(self):
        self.source.adapter_config = {"allow_empty": True, "partial_listing": True}
        self.source.save()
        self.assertTrue(self.run_ingest().success)
        self.listing(("other", "Vacancy: Driver", "Published 01.09.2026. Deadline 30.10.2026."))
        deleted = "https://emb.example/jobs/officer"
        def fetch_or_404(client, url):
            if url == deleted:
                request = httpx.Request("GET", url)
                raise httpx.HTTPStatusError("Not Found", request=request, response=httpx.Response(404, request=request))
            return self.fake_fetch(client, url)
        from .ingest import ingest_source
        with patch("board.ingest.fetch", side_effect=fetch_or_404), patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2)):
            self.assertTrue(ingest_source(self.source.pk).success)
        self.assertEqual(dict(self.source.jobs.values_list("title", "closed_reason")), {"Vacancy: Political Officer": "missing", "Vacancy: Driver": ""})

    def test_proven_job_published_and_closed_after_two_missing_scans(self):
        self.assertTrue(self.run_ingest().success)
        job = self.source.jobs.get()
        self.assertEqual((job.status, job.deadline, job.source_published_at), ("published", date(2026, 10, 30), date(2026, 9, 1)))
        self.listing(("other", "Vacancy: Driver", "Published 01.09.2026. Deadline 30.10.2026."))
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual((job.status, job.missing_scans), ("published", 1))
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual(job.status, "closed")

    def test_unconfirmed_empty_listing_does_not_close_live_jobs(self):
        self.run_ingest()
        self.listing()
        run = self.run_ingest()
        self.assertFalse(run.success)
        self.assertIn("suddenly empty", run.error)
        self.assertEqual(self.source.jobs.get().status, "published")
        self.source.adapter_config = {"allow_empty": True, "empty_text": "No vacancies"}
        self.source.save()
        self.pages[self.source.url] = "<p>No vacancies</p>"
        self.run_ingest()
        self.assertTrue(self.run_ingest().success)
        self.assertEqual(self.source.jobs.get().status, "closed")

    def test_failed_scan_never_closes(self):
        self.run_ingest()
        self.pages.pop(self.source.url)
        for _ in range(3):
            self.assertFalse(self.run_ingest().success)
        job = self.source.jobs.get()
        self.assertEqual((job.status, job.missing_scans), ("published", 0))
        self.source.refresh_from_db()
        self.assertEqual(self.source.status, "failing")

    def test_failed_detail_fails_whole_run(self):
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 30.10.2026."), ("driver", "Vacancy: Driver", ""))
        self.pages.pop("https://emb.example/jobs/driver")
        run = self.run_ingest()
        self.assertFalse(run.success)
        self.assertIn("Vacancy detail failed", run.error)
        self.assertFalse(self.source.jobs.exists())

    def test_excessive_detail_links_fail_before_fetching_and_keep_published_jobs(self):
        from .ingest import ingest_source, MAX_DETAIL_LINKS
        from .models import SourceDocument
        self.assertTrue(self.run_ingest().success)
        job = self.source.jobs.get()
        self.source.refresh_from_db()
        last_success = self.source.last_success_at
        documents = SourceDocument.objects.count()
        self.listing(*[(f"driver-{n}", "Vacancy: Driver", "Published 01.09.2026. Deadline 30.10.2026.") for n in range(MAX_DETAIL_LINKS + 1)])
        with patch("board.ingest.fetch", side_effect=self.fake_fetch) as fetched:
            run = ingest_source(self.source.pk)
        self.assertFalse(run.success)
        self.assertIn(f"More than {MAX_DETAIL_LINKS}", run.error)
        self.assertIsNotNone(run.finished_at)
        fetched.assert_called_once()
        job.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual((job.status, job.missing_scans), ("published", 0))
        self.assertEqual(self.source.last_success_at, last_success)
        self.assertEqual(SourceDocument.objects.count(), documents)
        self.assertEqual(self.source.jobs.count(), 1)

    def test_old_archives_are_skipped_before_detail_fetch(self):
        self.pages[self.source.url] += '<a href="/2025/09/driver">Vacancy: Driver 2026</a>'
        self.assertTrue(self.run_ingest().success)
        self.assertEqual(self.source.jobs.count(), 1)

    def test_expired_excluded_and_undated_leads(self):
        self.listing(("old", "Vacancy: Assistant", "Published 01.08.2026. Deadline 15.09.2026."), ("grant", "Scholarship vacancy", "Published 01.09.2026. Deadline 30.10.2026."), ("nodate", "Vacancy: Adviser", "Deadline 30.10.2026."))
        self.assertTrue(self.run_ingest().success)
        job = self.source.jobs.get()
        self.assertEqual((job.title, job.status, job.field_evidence["review_reason"]), ("Vacancy: Adviser", "review", "Godina objave nije potvrđena"))

    def test_manual_edit_survives_refresh(self):
        self.run_ingest()
        job = self.source.jobs.get()
        job.title, job.manually_edited_fields = "Political Officer (edited)", ["title"]
        job.save()
        self.listing(("officer", "Vacancy: Political Officer II", "Published 01.09.2026. Deadline 31.10.2026."))
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual((job.title, job.deadline), ("Political Officer (edited)", date(2026, 10, 31)))

    def run_on(self, day):
        from .ingest import ingest_source
        with patch("board.ingest.fetch", side_effect=self.fake_fetch), patch("board.ingest.timezone.localdate", return_value=day):
            return ingest_source(self.source.pk)

    def test_deadline_closes_and_extension_reopens(self):
        self.run_ingest()
        job = self.source.jobs.get()
        self.run_on(date(2026, 10, 31))
        job.refresh_from_db()
        self.assertEqual((job.status, job.closed_reason), ("closed", "deadline"))
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 15.11.2026."))
        self.run_on(date(2026, 10, 31))
        job.refresh_from_db()
        self.assertEqual((job.status, job.closed_reason, job.deadline), ("published", "", date(2026, 11, 15)))

    def test_manual_close_is_final(self):
        self.run_ingest()
        Job.objects.update(status="closed", closed_reason="manual")
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 15.11.2026."))
        self.run_ingest()
        self.assertEqual(self.source.jobs.get().status, "closed")

    def test_expire_jobs_clears_review_queue(self):
        from .ingest import expire_jobs
        from django.utils import timezone
        from datetime import timedelta
        Job.objects.create(source=self.source, canonical_url="https://emb.example/a", title="Expired lead", status="review", deadline=timezone.localdate() - timedelta(days=1))
        Job.objects.create(source=self.source, canonical_url="https://emb.example/b", title="Old undated lead", status="review", first_seen_at=timezone.now() - timedelta(days=61))
        Job.objects.create(source=self.source, canonical_url="https://emb.example/c", title="Fresh undated lead", status="review")
        expire_jobs()
        self.assertEqual(dict(Job.objects.values_list("title", "closed_reason")), {"Expired lead": "deadline", "Old undated lead": "stale", "Fresh undated lead": ""})

    def test_late_2026_lead_with_2027_deadline_goes_to_review(self):
        self.listing(("driver", "Vacancy: Driver", "Deadline 15.01.2027."))
        self.run_on(date(2026, 12, 10))
        job = self.source.jobs.get()
        self.assertEqual((job.status, job.deadline), ("review", date(2027, 1, 15)))

    def test_deadline_extended_into_2027_keeps_job_open(self):
        self.listing(("driver", "Vacancy: Driver", "Published 01.12.2026. Deadline 20.12.2026."))
        self.run_on(date(2026, 12, 10))
        self.listing(("driver", "Vacancy: Driver", "Published 01.12.2026. Deadline 20.12.2026, extended until 15.01.2027."))
        self.run_on(date(2026, 12, 18))
        from .ingest import expire_jobs
        with patch("board.ingest.timezone.localdate", return_value=date(2026, 12, 21)):
            expire_jobs()
        job = self.source.jobs.get()
        self.assertEqual((job.status, job.deadline), ("published", date(2027, 1, 15)))

    def test_contract_extension_is_not_a_deadline_extension(self):
        cases = [
            ("Deadline for applications: 15 October 2026. Initial contract of one year, may be extended until 31 December 2027.", date(2026, 10, 15)),
            ("Rok za prijave: 30.09.2026. Ugovor se može produžiti do 31.12.2027.", date(2026, 9, 30)),
            ("Deadline 20.12.2026, extended until 15.01.2027.", date(2027, 1, 15)),
            ("The deadline for applications has been extended to 20 October 2026.", date(2026, 10, 20)),
            ("Rok za prijavu je produžen do 25.10.2026.", date(2026, 10, 25)),
            ("Extended deadline: 5 November 2026", date(2026, 11, 5)),
            ("Deadline: 15 October 2026. Only shortlisted applications will be contacted. Contract may be extended until 31.12.2027", date(2026, 10, 15)),
            ("Vacancy: Driver. Fixed-term, may be extended until 31 December 2027. Deadline 15 October 2026", date(2026, 10, 15)),
            ("Oglas za posao. Ugovor može biti produžen do 31.12.2027. Rok 15.10.2026.", date(2026, 10, 15)),
            ("The position remains open until filled. Expected start: 1 January 2027", None),
            ("Applications received by email only. Published 1.10.2026", None),
            ("Applications will be accepted until 20 October 2026.", date(2026, 10, 20)),
            ("Deadline: 16:00 UTC+1 15/10/2026", date(2026, 10, 15)),
            ("Closing date: 12:00 PM (UTC+1), 15 October 2026", date(2026, 10, 15)),
        ]
        for text, expected in cases:
            self.assertEqual(parse_deadline(text), expected, text)

    def test_deadline_with_time_or_day_count_before_date(self):
        cases = [
            ("Deadline: 5 p.m., 15 March 2026", date(2026, 3, 15)),
            ("Closing date: 12:00 CET, 1 November 2026", date(2026, 11, 1)),
            ("Rok za prijavu: 15 dana od objave, najkasnije do 20.10.2026.", date(2026, 10, 20)),
            ("Deadline: 17:00 h, 15.03.2026", date(2026, 3, 15)),
        ]
        for text, expected in cases:
            self.assertEqual(parse_deadline(text), expected, text)

    def test_source_change_after_ai_keeps_human_closure(self):
        self.run_ingest()
        job = self.source.jobs.get()
        job.status, job.closed_reason, job.field_evidence = "closed", "manual", {**job.field_evidence, "ai_fields": ["city"]}
        job.save()
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 30.10.2026. Updated terms."))
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual((job.status, job.closed_reason), ("closed", "manual"))

    def test_closed_notice_withdraws_even_reviewed_job(self):
        self.run_ingest()
        Job.objects.update(last_reviewed_at=Job.objects.get().first_seen_at)
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 30.10.2026. Unfortunately, this position has been closed."))
        self.run_ingest()
        job = self.source.jobs.get()
        self.assertEqual((job.status, job.closed_reason), ("closed", "withdrawn"))

    def test_reviewed_job_back_to_review_when_source_changes_and_fails_checks(self):
        self.run_ingest()
        Job.objects.update(last_reviewed_at=Job.objects.get().first_seen_at)
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 30.10.2026. Duty station moved to Belgrade, Serbia."))
        self.pages["https://emb.example/jobs/officer"] = "<h1>Vacancy: Political Officer</h1><p>Duty station: Belgrade, Serbia. Published 01.09.2026. Deadline 30.10.2026.</p>"
        self.run_ingest()
        self.assertEqual(self.source.jobs.get().status, "review")

    def test_duplicate_anchor_fetched_once_with_first_title(self):
        self.pages[self.source.url] = '<a href="/jobs/officer">Vacancy: Political Officer</a><a href="/jobs/officer">Read more about this vacancy</a>'
        self.pages["https://emb.example/jobs/officer"] = "<p>Location: Sarajevo. Published 01.09.2026. Deadline 30.10.2026. Vacancy notice.</p>"
        self.run_ingest()
        from .models import SourceDocument
        self.assertEqual((self.source.jobs.get().title, SourceDocument.objects.count()), ("Vacancy: Political Officer", 1))

    def test_snapshot_stored_only_when_page_changes(self):
        from .models import SourceDocument
        self.run_ingest()
        self.run_ingest()
        self.assertEqual(SourceDocument.objects.count(), 1)
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 31.10.2026."))
        self.run_ingest()
        self.assertEqual(SourceDocument.objects.count(), 2)

    def test_overlong_link_skipped(self):
        slug = "x" * 1000
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 30.10.2026."), (slug, "Vacancy: Driver", "Published 01.09.2026. Deadline 30.10.2026."))
        self.assertTrue(self.run_ingest().success)
        self.assertEqual(list(self.source.jobs.values_list("title", flat=True)), ["Vacancy: Political Officer"])

    def test_review_reason_names_failed_checks(self):
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026."))
        self.pages["https://emb.example/jobs/officer"] = "<h1>Vacancy: Political Officer</h1><p>Published 01.09.2026. Duty station Belgrade.</p>"
        self.run_ingest()
        job = self.source.jobs.get()
        self.assertEqual((job.status, job.field_evidence["review_reason"]), ("review", "Lokacija u BiH nije pronađena; rok nije naveden"))

    def test_ai_fields_kept_and_changed_source_sent_to_review(self):
        self.run_ingest()
        job = self.source.jobs.get()
        job.city, job.field_evidence = "Banja Luka", {**job.field_evidence, "ai_fields": ["city"]}
        job.save()
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual((job.status, job.city), ("published", "Banja Luka"))
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 30.10.2026. Updated terms."))
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual((job.status, job.city, job.field_evidence["review_reason"]), ("review", "Banja Luka", "Izvor je promijenjen nakon AI obrade"))
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual(job.status, "review", "an unchanged later scan must not skip the human check")
        job.status, job.last_reviewed_at = "published", job.last_checked_at
        job.save()
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual(job.status, "published")

    def test_ai_requirements_dropped_without_review_when_source_changes(self):
        self.run_ingest()
        job = self.source.jobs.get()
        job.education_level, job.experience_years = "master", 5
        job.field_evidence = {**job.field_evidence, "ai_fields": ["education_level", "experience_years"], "education_level": "Master's degree", "experience_years": "5 years"}
        job.save()
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual((job.status, job.education_level, job.experience_years), ("published", "master", 5))
        self.listing(("officer", "Vacancy: Political Officer", "Published 01.09.2026. Deadline 30.10.2026. Updated terms."))
        self.run_ingest()
        job.refresh_from_db()
        self.assertEqual((job.status, job.education_level, job.experience_years, job.field_evidence["ai_fields"]), ("published", "", None, []))
        self.assertNotIn("education_level", job.field_evidence)


class GenericListingOptionsTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Ireland", kind="embassy")
        self.source = Source.objects.create(organization=organization, adapter="generic", url="https://www.ireland.ie/en/bosnia-herzegovina/sarajevo/about/job-opportunities/", adapter_config={"link_selector": "main a[href]", "path_contains": "/sarajevo/about/job-opportunities/", "any_title": True, "empty_text": "There are currently no vacancies"})

    def test_empty_note_required_and_any_title_kept(self):
        page = lambda body: BeautifulSoup(f"<main>{body}</main>", "html.parser")
        self.assertEqual(discover_links(None, self.source, page("There are currently no vacancies.")), [])
        with self.assertRaises(ValueError):
            discover_links(None, self.source, page("Page moved"))
        links = discover_links(None, self.source, page('<a href="/en/bosnia-herzegovina/sarajevo/about/job-opportunities/driver/">Driver</a>'))
        self.assertEqual([title for _, title in links], ["Driver"])

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_content_and_published_selectors(self, _):
        self.source.adapter_config = {"content_selector": ".article-page", "published_selector": ".article__info__date"}
        html = '<nav>Bosnia and Herzegovina news</nav><div class="article-page"><h1>Vacancy: National Programme Officer</h1><span class="article__info__date">25 Sep 2026</span><p>Duty station Sarajevo. Apply no later than 9 October 2026.</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        candidate = make_candidate(self.source, "https://www.ireland.ie/x", "Vacancy", soup.get_text(" ", strip=True), soup)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.title), (date(2026, 9, 25), date(2026, 10, 9), "Vacancy: National Programme Officer"))
        self.assertNotIn("news", candidate.text)
        self.assertTrue(candidate.eligible and candidate.year_proven)

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_published_from_meta_timestamp(self, _):
        self.source.adapter_config = {"content_selector": "article", "published_selector": "meta[property='article:published_time']"}
        html = '<head><meta property="article:published_time" content="2026-09-30T10:51:47+02:00"></head><aside>Local Branch Office Sarajevo</aside><article><h1>Vacancy: Programme Officer</h1><p>Duty station Pristina. Application Deadline: October 28, 2026</p></article>'
        soup = BeautifulSoup(html, "html.parser")
        candidate = make_candidate(self.source, "https://www.ireland.ie/y", "Vacancy", soup.get_text(" ", strip=True), soup)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 9, 30), date(2026, 10, 28), ""))
        self.assertFalse(candidate.eligible)

    def test_long_closing_phrase_parses(self):
        self.assertEqual(parse_deadline("The closing date for completed applications is 12 May 2026."), date(2026, 5, 12))


class DenmarkItalyAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        self.denmark = Source.objects.create(organization=organization, adapter="denmark", url="https://um.dk/Bosnien-Hercegovina/en/about-us/vacancies/")
        self.italy = Source.objects.create(organization=organization, adapter="italy", url="https://ambsarajevo.esteri.it/it/amministrazione-trasparente/bandi-di-concorso/")

    def test_denmark_note_and_same_host_links(self):
        self.assertEqual(discover_links(None, self.denmark, BeautifulSoup("<h1>Vacancies</h1><p>No current vacancies</p>", "html.parser")), [])
        with self.assertRaises(ValueError):
            discover_links(None, self.denmark, BeautifulSoup("<h1>Vacancies</h1><p>Page under construction</p>", "html.parser"))
        html = '<a href="/Bosnien-Hercegovina/en/about-us/vacancies/driver-position">Driver position</a><a href="https://jobs.example.com/x">Job portal</a>'
        self.assertEqual(discover_links(None, self.denmark, BeautifulSoup(html, "html.parser")), [("https://um.dk/Bosnien-Hercegovina/en/about-us/vacancies/driver-position", "Driver position")])

    def test_italy_open_selections_section(self):
        html = '<p><strong>Bandi e selezioni aperti (pubblicità legale)</strong></p><ul><li><a href="/it/news/dall_ambasciata/2026/04/avviso/">Selezione impiegati (scad. presentazione domande 20.03.2026)</a></li></ul>'
        links = discover_links(None, self.italy, BeautifulSoup(html, "html.parser"))
        self.assertEqual(links, [("https://ambsarajevo.esteri.it/it/news/dall_ambasciata/2026/04/avviso", "Selezione impiegati (scad. presentazione domande 20.03.2026)")])
        self.assertEqual(parse_deadline(links[0][1]), date(2026, 3, 20))
        with self.assertRaises(ValueError):
            discover_links(None, self.italy, BeautifulSoup("<p>Amministrazione trasparente</p>", "html.parser"))


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PublicViewTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        self.today = timezone.localdate()
        embassy = Organization.objects.create(name="Embassy A", kind="embassy")
        old = Organization.objects.create(name="Embassy Expired", kind="embassy")
        source = Source.objects.create(organization=embassy, url="https://a.example/jobs", adapter="generic", status="verified", enabled=True)
        old_source = Source.objects.create(organization=old, url="https://b.example/jobs", adapter="generic", status="verified", enabled=True)
        from datetime import timedelta
        Job.objects.create(source=source, canonical_url="https://a.example/1", title="Driver", city="Sarajevo", status="published", deadline=self.today + timedelta(days=5))
        Job.objects.create(source=source, canonical_url="https://a.example/2", title="Legal Consultant", city="Mostar", opportunity_type="consultancy", status="published", deadline=self.today + timedelta(days=5))
        Job.objects.create(source=old_source, canonical_url="https://b.example/1", title="Old Clerk", city="Tuzla", status="published", deadline=self.today - timedelta(days=1))

    def test_type_filter_and_visible_only_dropdowns(self):
        response = self.client.get("/", {"type": "consultancy"})
        self.assertContains(response, "Legal Consultant")
        self.assertNotContains(response, ">Driver</a></h3>", html=False)
        self.assertNotContains(response, "Embassy Expired")
        self.assertNotContains(response, "Tuzla")
        self.assertContains(response, 'value="consultancy" selected')
        self.assertNotContains(response, 'value="paid_internship"')

    def test_deadline_sort_badges_and_city_search(self):
        from datetime import timedelta
        Job.objects.filter(title="Driver").update(deadline=self.today + timedelta(days=12))
        Job.objects.filter(title="Legal Consultant").update(deadline=self.today)
        content = self.client.get("/", {"sort": "deadline"}).content.decode()
        self.assertLess(content.index("Legal Consultant"), content.index(">Driver</a></h3>"))
        self.assertIn("Ističe danas", content)
        self.assertIn("Novo", content)
        city = self.client.get("/", {"q": "Mostar"}).content.decode()
        self.assertIn("Legal Consultant", city)
        self.assertNotIn(">Driver</a></h3>", city)

    def test_search_ignores_case_and_diacritics(self):
        Job.objects.filter(title="Driver").update(title="Vozač – Brčko", city="Brčko")
        for query in ("vozac", "BRCKO", "Brčko"):
            self.assertIn("Vozač – Brčko", self.client.get("/", {"q": query}).content.decode(), query)
        self.assertNotIn("Vozač – Brčko", self.client.get("/", {"q": "Mostar"}).content.decode())

    def test_search_matches_every_word_anywhere(self):
        Job.objects.filter(title="Driver").update(title="Driver, Field Office", city="Brčko")
        for query in ("driver brcko", "brcko driver", "  DRIVER   office "):
            self.assertIn("Driver, Field Office", self.client.get("/", {"q": query}).content.decode(), query)
        self.assertNotIn("Driver, Field Office", self.client.get("/", {"q": "driver mostar"}).content.decode())

    def test_fold(self):
        from .text import fold
        self.assertEqual([fold(word) for word in ("Švicarska", "ĐURĐEVDAN", "djurdjevdan", "Žepče")], ["svicarska", "durdevdan", "durdevdan", "zepce"])

    def test_pages_keep_active_filters_and_reject_missing_pages(self):
        from datetime import timedelta
        source = Source.objects.get(url="https://a.example/jobs")
        for number in range(25):
            Job.objects.create(source=source, canonical_url=f"https://a.example/bulk/{number}", title=f"Bulk Officer {number}", city="Sarajevo", status="published", deadline=self.today + timedelta(days=10))
        first = self.client.get("/", {"city": "Sarajevo", "sort": "deadline"})
        self.assertContains(first, 'href="?city=Sarajevo&amp;sort=deadline&amp;page=2"')
        self.assertNotContains(first, "employer=&amp;")
        second = self.client.get("/", {"city": "Sarajevo", "sort": "deadline", "page": "2"})
        self.assertContains(second, 'href="?city=Sarajevo&amp;sort=deadline&amp;page=1"')
        self.assertContains(second, "Stranica 2 od 2")
        self.assertContains(self.client.get("/", {"page": "2"}), 'href="?page=1"')
        for page in ("99", "0", "abc"):
            self.assertEqual(self.client.get("/", {"page": page}).status_code, 404, page)
        self.assertEqual(self.client.get("/", {"q": "nothing-matches-this"}).status_code, 200)

    def test_filtered_page_links_its_feed_and_a_reset(self):
        content = self.client.get("/", {"city": "Mostar", "page": "1"}).content.decode()
        self.assertIn('href="/feed/?city=Mostar"', content)
        self.assertIn("Poništi sve", content)
        self.assertIn('<span class="chip">Mostar<a href="/" aria-label="Ukloni grad: Mostar">', content)
        self.assertIn('<span class="visually-hidden">: Legal Consultant</span>', content)
        plain = self.client.get("/").content.decode()
        self.assertNotIn("Poništi sve", plain)
        self.assertIn('type="application/atom+xml" title="DiplomacyJobs – novi oglasi" href="/feed/"', plain)
        sources = self.client.get("/sources/").content.decode()
        self.assertIn('<meta property="og:description" content="Koje službene izvore', sources)

    def test_filter_chips_remove_one_filter_and_keep_the_rest(self):
        content = self.client.get("/", {"city": "Mostar", "type": "consultancy", "scope": "national", "sort": "deadline"}).content.decode()
        self.assertIn('aria-label="Ukloni grad: Mostar"', content)
        self.assertIn('href="/?type=consultancy&amp;scope=national&amp;sort=deadline" aria-label="Ukloni grad: Mostar"', content)
        self.assertIn('href="/?city=Mostar&amp;type=consultancy&amp;sort=deadline" aria-label="Ukloni poziciju: Nacionalne"', content)
        self.assertIn('<a class="clear-all" href="/?sort=deadline">', content)
        # Scope sits behind the disclosure, so it opens and counts one hidden filter.
        self.assertIn('<details class="more-filters" open>', content)
        self.assertIn('<span class="filter-count">1<', content)
        self.assertIn('<a href="/?city=Mostar&amp;type=consultancy&amp;scope=national&amp;sort=deadline" aria-current="true">', content)
        self.assertIn('<details class="more-filters">', self.client.get("/", {"city": "Mostar"}).content.decode())

    def test_deadline_countdown_agrees_with_the_number(self):
        from datetime import timedelta
        from .templatetags.board_extras import deadline
        job = Job.objects.get(title="Driver")
        for days, text, urgency in ((0, "Ističe danas", "today"), (1, "Ističe sutra", "today"), (2, "Još 2 dana", "soon"), (7, "Još 7 dana", "soon"), (21, "Još 21 dan", "open"), (25, "Još 25 dana", "open")):
            job.days_left = days
            self.assertEqual((deadline(job)["countdown"], deadline(job)["urgency"]), (text, urgency), days)
        job.days_left = -1
        self.assertEqual(deadline(job)["countdown"], "")

    def test_job_page_has_a_summary_and_apply_bar_only_while_current(self):
        job = Job.objects.get(title="Driver")
        page = self.client.get(job.get_absolute_url()).content.decode()
        self.assertIn('<dl class="key-facts">', page)
        self.assertIn('<div class="apply-bar"><div class="deadline deadline-bar">', page)
        self.assertIn("Još 5 dana", page)
        old = Job.objects.get(title="Old Clerk")
        closed = self.client.get(old.get_absolute_url()).content.decode()
        self.assertNotIn('class="apply-bar"', closed)
        self.assertNotIn("deadline-countdown", closed)

    def test_feed_lists_visible_jobs_with_filters(self):
        feed = self.client.get("/feed/")
        self.assertEqual(feed["Content-Type"].split(";")[0], "application/atom+xml")
        content = feed.content.decode()
        self.assertIn("Driver – Embassy A", content)
        self.assertIn("<id>tag:testserver,2026:job-", content)
        self.assertNotIn("Old Clerk", content)
        self.assertNotIn("Driver", self.client.get("/feed/", {"type": "consultancy"}).content.decode())
        self.assertContains(self.client.get("/"), 'href="/feed/"')

    def test_scope_filter(self):
        Job.objects.filter(title="Driver").update(scope="national")
        content = self.client.get("/", {"scope": "national"}).content.decode()
        self.assertIn(">Driver</a></h3>", content)
        self.assertNotIn("Legal Consultant", content)
        self.assertIn("Nacionalna pozicija", content)

    def test_unknown_type_ignored_and_sources_page_renders(self):
        self.assertContains(self.client.get("/", {"type": "bogus"}), "Driver")
        self.assertContains(self.client.get("/sources/"), "Embassy A")


class ScrapeLockTests(TestCase):
    def test_stale_lock_removed_fresh_lock_respected(self):
        import io
        import os
        import time
        from pathlib import Path
        from django.core.management import call_command
        from django.core.management.base import CommandError
        lock = Path(os.environ.get("TEMP", ".")) / "diplomacyjobs-scrape.lock" if os.name == "nt" else Path("/tmp/diplomacyjobs-scrape.lock")
        self.addCleanup(lock.unlink, missing_ok=True)
        lock.write_text("1")
        with self.assertRaises(CommandError):
            call_command("scrape_jobs", stdout=io.StringIO(), stderr=io.StringIO())
        old = time.time() - 7 * 60 * 60
        os.utime(lock, (old, old))
        call_command("scrape_jobs", stdout=io.StringIO(), stderr=io.StringIO())
        self.assertFalse(lock.exists())


class AdminActionTests(TestCase):
    def test_renewal_restores_visibility_only_for_selected_undated_jobs(self):
        from datetime import timedelta
        from django.utils import timezone
        from .admin import renew_jobs
        from .views import visible_jobs
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        source = Source.objects.create(organization=organization, url="https://a.example/jobs", enabled=True)
        old = timezone.now() - timedelta(days=40)
        selected = Job.objects.create(source=source, canonical_url="https://a.example/1", title="Renew", status="published", first_seen_at=old)
        unselected = Job.objects.create(source=source, canonical_url="https://a.example/2", title="Leave", status="published", first_seen_at=old)
        dated = Job.objects.create(source=source, canonical_url="https://a.example/3", title="Expired", status="published", first_seen_at=old, deadline=timezone.localdate() - timedelta(days=1))
        self.assertFalse(visible_jobs().exists())
        renew_jobs(None, None, Job.objects.filter(pk__in=[selected.pk, dated.pk]))
        self.assertEqual(list(visible_jobs().values_list("pk", flat=True)), [selected.pk])
        for job in (selected, unselected, dated):
            job.refresh_from_db()
        self.assertIsNotNone(selected.last_reviewed_at)
        self.assertIsNone(unselected.last_reviewed_at)
        self.assertIsNone(dated.last_reviewed_at)
        self.assertEqual(selected.status, "published")

    def test_publish_skips_expired_and_close_is_manual(self):
        from datetime import timedelta
        from unittest.mock import Mock
        from django.utils import timezone
        from .admin import close_jobs, publish_jobs
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        source = Source.objects.create(organization=organization, url="https://a.example/jobs", enabled=True)
        Job.objects.create(source=source, canonical_url="https://a.example/1", title="Open", deadline=timezone.localdate() + timedelta(days=3))
        Job.objects.create(source=source, canonical_url="https://a.example/2", title="Expired", deadline=timezone.localdate() - timedelta(days=3))
        admin = Mock()
        publish_jobs(admin, None, Job.objects.all())
        self.assertEqual(dict(Job.objects.values_list("title", "status")), {"Open": "published", "Expired": "review"})
        admin.message_user.assert_called_once()
        disabled = Source.objects.create(organization=organization, url="https://off.example/jobs", enabled=False)
        Job.objects.create(source=disabled, canonical_url="https://off.example/1", title="Off")
        admin.reset_mock()
        publish_jobs(admin, None, Job.objects.filter(title="Off"))
        self.assertEqual(Job.objects.get(title="Off").status, "review")
        admin.message_user.assert_called_once()
        Job.objects.create(source=source, canonical_url="https://a.example/3", title="Tirana", field_evidence={"review_reason": "Lokacija u BiH nije pronađena"})
        Job.objects.create(source=source, canonical_url="https://a.example/4", title="Clean", field_evidence={"review_reason": ""})
        admin.reset_mock()
        publish_jobs(admin, None, Job.objects.filter(title__in=["Tirana", "Clean"]))
        self.assertEqual(dict(Job.objects.filter(title__in=["Tirana", "Clean"]).values_list("title", "status")), {"Tirana": "review", "Clean": "published"})
        admin.message_user.assert_called_once()
        self.assertIn("Lokacija u BiH nije pronađena", admin.message_user.call_args.args[1])
        close_jobs(admin, None, Job.objects.filter(title="Open"))
        job = Job.objects.get(title="Open")
        self.assertEqual((job.status, job.closed_reason), ("closed", "manual"))
        self.assertIsNotNone(job.last_reviewed_at)

    def test_bulk_actions_are_recorded_in_admin_history(self):
        from datetime import timedelta
        from django.contrib.admin.models import LogEntry
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        source = Source.objects.create(organization=organization, url="https://a.example/jobs", enabled=True)
        clean = Job.objects.create(source=source, canonical_url="https://a.example/1", title="Clean", deadline=timezone.localdate() + timedelta(days=3))
        flagged = Job.objects.create(source=source, canonical_url="https://a.example/2", title="Tirana", deadline=timezone.localdate() + timedelta(days=3), field_evidence={"review_reason": "Lokacija u BiH nije pronađena"})
        reviewer = get_user_model().objects.create_superuser("reviewer", "", "pw")
        self.client.force_login(reviewer)
        self.client.post("/admin/board/job/", {"action": "publish_jobs", "_selected_action": [clean.pk, flagged.pk]})
        self.assertEqual(list(LogEntry.objects.values_list("object_id", "user_id", "change_message")), [(str(clean.pk), reviewer.pk, "Objavljeno skupnom akcijom.")])
        self.client.post("/admin/board/job/", {"action": "close_jobs", "_selected_action": [flagged.pk]})
        self.assertEqual(LogEntry.objects.filter(object_id=str(flagged.pk)).get().change_message, "Zatvoreno skupnom akcijom.")


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class StaleSourceTests(TestCase):
    def test_stale_source_unavailable_and_scrape_health_fails(self):
        from datetime import timedelta
        from django.utils import timezone
        organization = Organization.objects.create(name="Embassy Stale", kind="embassy")
        now = timezone.now()
        source = Source.objects.create(organization=organization, url="https://a.example/jobs", adapter="generic", status="verified", enabled=True, last_success_at=now, last_attempt_at=now)
        self.assertEqual(self.client.get("/health/scrape/").status_code, 200)
        self.assertContains(self.client.get("/sources/", {"status": "empty"}), "Embassy Stale")
        Source.objects.filter(pk=source.pk).update(last_success_at=timezone.now() - timedelta(hours=49), last_attempt_at=timezone.now() - timedelta(hours=49))
        self.assertEqual(self.client.get("/health/scrape/").status_code, 503)
        self.assertContains(self.client.get("/sources/", {"status": "unavailable"}), "Embassy Stale")
        self.assertEqual(self.client.get("/health/").status_code, 200)


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AdminReviewQueueTests(TestCase):
    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_change_view_shows_what_changed_on_the_source(self):
        from datetime import timedelta
        from django.contrib.auth.models import User
        from django.utils import timezone
        from .models import SourceDocument
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "x"))
        source = Source.objects.create(organization=Organization.objects.create(name="Embassy", kind="embassy"), url="https://a.example/jobs")
        job = Job.objects.create(source=source, canonical_url="https://a.example/1", title="Driver", status="review")
        SourceDocument.objects.create(source=source, url=job.canonical_url, content_hash="a", text="Driver. Deadline 10.10.2026. Location Sarajevo.")
        SourceDocument.objects.filter(content_hash="a").update(fetched_at=timezone.now() - timedelta(days=1))
        SourceDocument.objects.create(source=source, url=job.canonical_url, content_hash="b", text="Driver. Deadline 20.10.2026. Location Sarajevo.")
        response = self.client.get(f"/admin/board/job/{job.pk}/change/")
        self.assertContains(response, "-Deadline 10.10.2026.")
        self.assertContains(response, "+Deadline 20.10.2026.")
        self.assertNotContains(response, "Location Sarajevo.</div>")

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_run_and_snapshot_lists_filter_and_skip_text(self):
        from django.contrib.auth.models import User
        from .models import ScrapeRun, SourceDocument
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "x"))
        source = Source.objects.create(organization=Organization.objects.create(name="Embassy", kind="embassy"), url="https://a.example/jobs", adapter="generic")
        ScrapeRun.objects.create(source=source, success=True, error="")
        ScrapeRun.objects.create(source=source, success=False, error="HTTP 503 from listing")
        failures = self.client.get("/admin/board/scraperun/", {"success__exact": "0"})
        self.assertContains(failures, "HTTP 503 from listing")
        self.assertContains(failures, "1 scrape run")
        document = SourceDocument.objects.create(source=source, url="https://a.example/1", content_hash="a", text="UNIQUE-SNAPSHOT-TEXT")
        self.assertNotContains(self.client.get("/admin/board/sourcedocument/"), "UNIQUE-SNAPSHOT-TEXT")
        self.assertContains(self.client.get(f"/admin/board/sourcedocument/{document.pk}/change/"), "UNIQUE-SNAPSHOT-TEXT")

    def test_changelist_shows_reason_and_deadline_filter(self):
        from datetime import timedelta
        from django.contrib.auth.models import User
        from django.utils import timezone
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "x"))
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        source = Source.objects.create(organization=organization, url="https://a.example/jobs")
        Job.objects.create(source=source, canonical_url="https://a.example/1", title="Undated lead", status="review", field_evidence={"review_reason": "Godina objave nije potvrđena"})
        Job.objects.create(source=source, canonical_url="https://a.example/2", title="Past lead", status="review", deadline=timezone.localdate() - timedelta(days=2))
        response = self.client.get("/admin/board/job/", {"rok": "none"})
        self.assertContains(response, "Godina objave nije potvrđena")
        self.assertContains(response, "https://a.example/1")
        self.assertNotContains(response, "Past lead")

    def test_source_list_shows_last_run(self):
        from django.contrib.auth.models import User
        from .models import ScrapeRun
        self.client.force_login(User.objects.create_superuser("admin2", "b@example.com", "x"))
        source = Source.objects.create(organization=Organization.objects.create(name="Org", kind="embassy"), url="https://b.example/jobs")
        ScrapeRun.objects.create(source=source, success=False, error="Unusable response: HTTP 202")
        self.assertContains(self.client.get("/admin/board/source/"), "Greška: Unusable response: HTTP 202")
        for index in range(10):
            ScrapeRun.objects.create(source=Source.objects.create(organization=source.organization, url=f"https://c{index}.example/jobs"), success=True, candidates=index)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as queries:
            self.client.get("/admin/board/source/")
        self.assertLess(len(queries), 12, "source list must not query runs per row")


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class SeoTests(TestCase):
    def test_meta_robots_and_sitemap(self):
        page = self.client.get("/sources/").content.decode()
        self.assertIn('<meta name="description" content="Koje službene izvore', page)
        self.assertIn('<link rel="canonical" href="http://testserver/sources/">', page)
        self.assertIn('<meta property="og:description" content="Provjereni oglasi', self.client.get("/").content.decode())
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /admin/\n", robots)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", robots)
        self.assertContains(self.client.get("/sitemap.xml"), "<loc>http://testserver/sources/</loc>")

    def test_public_base_url_overrides_the_request_host(self):
        with override_settings(PUBLIC_BASE_URL="https://jobs.example.com"):
            self.assertIn('<link rel="canonical" href="https://jobs.example.com/sources/">', self.client.get("/sources/").content.decode())
            self.assertIn("Sitemap: https://jobs.example.com/sitemap.xml", self.client.get("/robots.txt").content.decode())
            self.assertContains(self.client.get("/sitemap.xml"), "<loc>https://jobs.example.com/</loc>")


class CityTests(TestCase):
    def test_spellings_and_labelled_station(self):
        from .ingest import LOCATION, city_name
        cases = [
            ("Embassy in Sarajevo. Vacancy: Driver. Duty station: Banja Luka office", "Banja Luka"),
            ("Location: Banjaluka", "Banja Luka"),
            ("Brcko District of BiH", "Brčko"),
            ("Field office Bihac", "Bihać"),
            ("Mjesto rada: Goražde", "Goražde"),
            ("Duty Station : Tuzla", "Tuzla"),
            ("Mjesto rada: u Sarajevu", "Sarajevo"),
            ("Radno mjesto u Banjoj Luci", "Banja Luka"),
            ("Kancelarija u Mostaru", "Mostar"),
        ]
        for text, expected in cases:
            self.assertTrue(LOCATION.search(text), text)
            self.assertEqual(city_name(text), expected, text)

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_portal_adapters_accept_titles_without_job_words(self, _):
        organization = Organization.objects.create(name="Agency", kind="international")
        for adapter in ("taleo", "bamboohr", "rmk"):
            source = Source.objects.create(organization=organization, adapter=adapter, url=f"https://{adapter}.example/jobs")
            candidate = make_candidate(source, f"https://{adapter}.example/jobs/1", "Forensic Anthropologist", "Forensic Anthropologist. Location: Sarajevo, Bosnia and Herzegovina. Published 2026-09-30. Closing date 2026-12-01.", None)
            self.assertTrue(candidate.eligible, adapter)


class RecruitmentScopeTests(TestCase):
    def test_markers_decide_and_conflicts_stay_unknown(self):
        from .ingest import recruitment_scope
        cases = [
            ("Project Associate", "Agency: UNDP. Grade: NPSA-9. Vacancy Type: National Personnel Service Agreement.", "national"),
            ("Chief, General Services (S3)", "", "international"),
            ("Purchasing Administrator", "Post no. CL FIN 0056 Grade: LCH-6", "national"),
            ("Senior Project Officer", "Recruitment type: External recruitment (international)", "international"),
            ("Driver", "Licence categories B and D1 required.", ""),
            ("Programme Officer (P3 / NOC)", "", ""),
            ("Programme Associate", "Applicant(s) must be citizens of Bosnia and Herzegovina.", ""),
            ("Finance Assistant, GS-5", "National(s) of Bosnia and Herzegovina only.", "national"),
            ("Project Assistant, SB-3", "", "national"),
            ("VA26P127V01 - Project Management Assistant - LS2", "", "national"),
            ("VA26P172V01 Senior Project Manager (IP4)", "", "international"),
            ("Programme Associate", "Contract type: Service Contract, SC-7.", "national"),
        ]
        for title, text, expected in cases:
            self.assertEqual(recruitment_scope(title, text), expected, title)


def uncareers_api(request):
    body = json.loads(request.content)
    page = body["pagination"]["page"]
    sarajevo = {"jobId": 300001, "postingTitle": "Coordination Officer, NOB", "jobLevel": "NO-B", "dutyStation": [{"description": "SARAJEVO"}], "startDate": "2026-09-30T04:00:00.000Z", "endDate": "2026-10-15T03:59:59.000Z", "dept": {"name": "Resident Coordinator Office"}, "jobDescription": "<p>Coordination.</p>"}
    vienna = {"jobId": 300002, "postingTitle": "Accounting Assistant, G4", "dutyStation": [{"description": "VIENNA"}], "startDate": "2026-10-01T04:00:00.000Z", "endDate": "2026-10-09T03:59:59.000Z"}
    return httpx.Response(200, json={"data": {"count": 101, "list": [{**vienna, "jobId": 200000 + n} for n in range(100)] if page == 0 else [sarajevo]}})


class UnCareersAdapterTests(TestCase):
    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_pages_read_and_bih_station_kept(self, _):
        organization = Organization.objects.create(name="UN", kind="international")
        source = Source.objects.create(organization=organization, adapter="uncareers", url="https://careers.un.org/jobopening?language=en")
        evidence = {}
        with httpx.Client(transport=httpx.MockTransport(uncareers_api)) as client:
            links = discover_links(client, source, None, evidence)
        self.assertEqual(links, [("https://careers.un.org/jobSearchDescription/300001?language=en", "Coordination Officer, NOB")])
        candidate = make_candidate(source, links[0][0], links[0][1], evidence[links[0][0]], None)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city, candidate.scope), (date(2026, 9, 30), date(2026, 10, 14), "Sarajevo", "national"))
        self.assertTrue(candidate.eligible and candidate.year_proven)


def csod_site(request):
    if request.url.host == "worldbankgroup.csod.com":
        return httpx.Response(200, text='<script>csod.context={"token":"anon123","cloud":"https://us.api.csod.com/"}</script>', headers={"content-type": "text/html"})
    assert request.headers["Authorization"] == "Bearer anon123"
    rows = [{"requisitionId": 38336, "displayJobTitle": "Operations Analyst", "locations": [{"city": "Sarajevo", "country": "BA"}], "postingEffectiveDate": "9/18/2026", "postingExpirationDate": "10/9/2026", "externalDescription": "<p>Analyst role.</p>"}, {"requisitionId": 38502, "displayJobTitle": "Finance Analyst", "locations": [{"city": "Dakar", "country": "SN"}]}]
    return httpx.Response(200, json={"data": {"totalCount": 2, "requisitions": rows}})


class UnCareersRetryTests(TestCase):
    @patch("board.ingest.time.sleep")
    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_gateway_timeouts_are_retried_then_give_up(self, _, sleep):
        organization = Organization.objects.create(name="UN", kind="international")
        source = Source.objects.create(organization=organization, adapter="uncareers", url="https://careers.un.org/jobopening?language=en")
        calls = []
        def flaky(request):
            calls.append(request)
            return httpx.Response(504, text="upstream request timeout") if len(calls) in (1, 3) else uncareers_api(request)
        with httpx.Client(transport=httpx.MockTransport(flaky)) as client:
            self.assertEqual(len(discover_links(client, source, None, {})), 1)
        self.assertEqual(len(calls), 4)
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(504, text="upstream request timeout"))) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                discover_links(client, source, None, {})
        # A refusal is not retried.
        sleep.reset_mock()
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403))) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                discover_links(client, source, None, {})
        sleep.assert_not_called()


class UnCareersShortPageTests(TestCase):
    def test_fewer_rows_than_count_fails(self):
        organization = Organization.objects.create(name="UN", kind="international")
        source = Source.objects.create(organization=organization, adapter="uncareers", url="https://careers.un.org/jobopening?language=en")
        def short_pages(request):
            page = json.loads(request.content)["pagination"]["page"]
            rows = [{"jobId": page * 50 + n, "dutyStation": [{"description": "VIENNA"}]} for n in range(50)] if page < 2 else []
            return httpx.Response(200, json={"data": {"count": 150, "list": rows}})
        with httpx.Client(transport=httpx.MockTransport(short_pages)) as client:
            with self.assertRaisesRegex(ValueError, "150 openings"):
                discover_links(client, source, None, {})


def taleo_site(request):
    if request.url.path.endswith("/searchjobs"):
        assert request.headers["tz"] == "GMT+01:00"
        page = json.loads(request.content)["pageNo"]
        geneva = [{"contestNo": str(2600000 + n), "column": [f"Officer {n}", '["Switzerland-Geneva"]', "Sep 30, 2026, 9:00:00 AM"]} for n in range(2)]
        sarajevo = {"contestNo": "2604321", "column": ["National Professional Officer (Health Systems)", '["Bosnia and Herzegovina-Sarajevo"]', "Sep 29, 2026, 4:12:00 PM"]}
        rows = geneva if page == 1 else [sarajevo]
        return httpx.Response(200, json={"requisitionList": rows, "pagingData": {"currentPageNo": page, "pageSize": 2, "totalCount": 4}})
    assert request.url.params["job"] == "2604321"
    fields = ["ftlx0", "National Professional Officer (Health Systems)", "NO-B", "Sep 29, 2026, 4%5C:12%5C:00 PM", "Sep 29, 2026, 4%5C:12%5C:00 PM", "Oct 13, 2026, 10%5C:59%5C:00 PM", "Oct 13, 2026, 10%5C:59%5C:00 PM", "Bosnia and Herzegovina-Sarajevo", "%3Cp%3EThe incumbent supports the WHO Country Office in Bosnia and Herzegovina, Sarajevo, on health system reform and coordination with national authorities.%3C/p%3E"]
    page = f'<html><body><input type="hidden" id="initialHistory" value="{"!|!".join(fields)}"></body></html>'
    return httpx.Response(200, text=page, headers={"content-type": "text/html"})


class TaleoAdapterTests(TestCase):
    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_pages_read_and_bih_row_dated_from_detail(self, _):
        organization = Organization.objects.create(name="WHO", kind="international")
        source = Source.objects.create(organization=organization, adapter="taleo", url="https://careers.who.int/careersection/ex/jobsearch.ftl", adapter_config={"portal": "101430233"})
        evidence = {}
        with httpx.Client(transport=httpx.MockTransport(taleo_site)) as client:
            links = discover_links(client, source, None, evidence)
        self.assertEqual(links, [("https://careers.who.int/careersection/ex/jobdetail.ftl?job=2604321", "National Professional Officer (Health Systems)")])
        candidate = make_candidate(source, links[0][0], links[0][1], evidence[links[0][0]], None)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 9, 29), date(2026, 10, 13), "Sarajevo"))
        self.assertTrue(candidate.eligible and candidate.year_proven)

    def test_both_taleo_date_styles(self):
        from .ingest import TALEO_DATE, taleo_date
        self.assertEqual([taleo_date(TALEO_DATE.match(value).group(0)) for value in ("Oct 23, 2026, 10:59:00 PM", "23/Oct/2026, 10:59:00 PM")], [date(2026, 10, 23)] * 2)

    def test_portal_required(self):
        organization = Organization.objects.create(name="WHO", kind="international")
        source = Source.objects.create(organization=organization, adapter="taleo", url="https://careers.who.int/careersection/ex/jobsearch.ftl")
        with self.assertRaisesRegex(ValueError, "portal"):
            discover_links(None, source, None, {})


def bamboohr_site(request):
    if request.url.path == "/careers/list":
        return httpx.Response(200, json={"result": [{"id": "350", "jobOpeningName": "Forensic Data Officer", "location": {"city": None, "state": None}}, {"id": "341", "jobOpeningName": "Finance Assistant", "location": {"city": None}}]})
    details = {
        "350": {"jobOpeningName": "Forensic Data Officer", "jobOpeningStatus": "Open", "location": {"city": "Sarajevo", "state": "Federation of Bosnia and Herzegovina"}, "datePosted": "2026-09-25", "employmentStatusLabel": "Full-time, fixed", "description": "<p>Applications are accepted until 20 October 2026.</p>"},
        "341": {"jobOpeningName": "Finance Assistant", "jobOpeningStatus": "Open", "location": {"city": "Turhenivska Street 15", "state": "Kyiv"}, "datePosted": "2026-09-02"},
    }
    return httpx.Response(200, json={"result": {"jobOpening": details[request.url.path.split("/")[2]]}})


class BambooHrAdapterTests(TestCase):
    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_detail_address_decides_and_dates_read(self, _):
        organization = Organization.objects.create(name="ICMP", kind="international")
        source = Source.objects.create(organization=organization, adapter="bamboohr", url="https://icmp.bamboohr.com/careers")
        evidence = {}
        with httpx.Client(transport=httpx.MockTransport(bamboohr_site)) as client:
            links = discover_links(client, source, None, evidence)
        self.assertEqual(links, [("https://icmp.bamboohr.com/careers/350", "Forensic Data Officer")])
        candidate = make_candidate(source, links[0][0], links[0][1], evidence[links[0][0]], None)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 9, 25), date(2026, 10, 20), "Sarajevo"))
        self.assertTrue(candidate.eligible and candidate.year_proven)


def rmk_row(path, title, location, posted):
    return f'<tr class="data-row"><td><a class="jobTitle-link" href="/job/{path}/">{title}</a></td><td><span class="jobLocation">{location}</span></td><td><span class="jobDate">{posted}</span></td></tr>'


class RmkAdapterTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="UNESCO", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="rmk", url="https://careers.unesco.org/go/All-jobs-openings/784002/")

    def test_pages_followed_and_bih_row_kept(self):
        first = BeautifulSoup('<span class="paginationLabel">Results 1 – 1 of 2</span>' + rmk_row("Paris-Officer/1", "Officer", "Paris, France", "1 Oct 2026"), "html.parser")
        second = BeautifulSoup('<span class="paginationLabel">Results 2 – 2 of 2</span>' + rmk_row("Sarajevo-Project-Assistant/2", "Project Assistant", "Sarajevo, Bosnia and Herzegovina", "29 Sept 2026"), "html.parser")
        evidence = {}
        with patch("board.ingest.fetch", return_value=("", second)) as fetch_page:
            links = discover_links(None, self.source, first, evidence)
        self.assertEqual(fetch_page.call_args.args[1], "https://careers.unesco.org/go/All-jobs-openings/784002/1/")
        self.assertEqual(links, [("https://careers.unesco.org/job/Sarajevo-Project-Assistant/2", "Project Assistant")])
        with patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2)):
            candidate = make_candidate(self.source, links[0][0], links[0][1], "Project Assistant Duty Station : Sarajevo Application deadline (Midnight UTC−5 Time) : 30/10/2026", None, evidence[links[0][0]])
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 9, 29), date(2026, 10, 30), "Sarajevo"))

    def test_ignored_offset_fails_instead_of_looping(self):
        first = BeautifulSoup('<span class="paginationLabel">Results 1 – 1 of 2</span>' + rmk_row("Paris-Officer/1", "Officer", "Paris, France", "1 Oct 2026"), "html.parser")
        with patch("board.ingest.fetch", return_value=("", first)) as fetch_page, self.assertRaisesRegex(ValueError, "1 of 2"):
            discover_links(None, self.source, first, {})
        self.assertEqual(fetch_page.call_count, 1)

    def test_short_listing_fails(self):
        first = BeautifulSoup('<span class="paginationLabel">Results 1 – 1 of 3</span>' + rmk_row("Paris-Officer/1", "Officer", "Paris, France", "1 Oct 2026"), "html.parser")
        with patch("board.ingest.fetch", return_value=("", BeautifulSoup("", "html.parser"))), self.assertRaisesRegex(ValueError, "1 of 3"):
            discover_links(None, self.source, first, {})


class RaiAdapterTests(TestCase):
    def test_current_boxes_and_open_vacancy_rows(self):
        organization = Organization.objects.create(name="RAI", kind="international")
        source = Source.objects.create(organization=organization, adapter="rai", url="https://rai-see.org/tenders-and-vacancies/")
        html = (
            '<div class="info_box"><h4>Project Officer (Sarajevo)</h4><a href="/php_sets/uploads/2026/10/Vacancy_PO.pdf">Read more</a></div>'
            '<div class="info_box"><h4>Internship Program - Currently closed</h4><a href="/internship/">More</a></div>'
            '<table><tr><th>Year</th><th>Title</th><th>Type</th><th>Status</th></tr>'
            '<tr><td>2026</td><td><a href="/php_sets/uploads/2026/09/Legal_Expert.pdf">Legal Expert</a></td><td>Consultancy</td><td>Open</td></tr>'
            '<tr><td>2026</td><td><a href="/php_sets/uploads/2026/01/Comms.pdf">Communications Officer</a></td><td>Vacancy</td><td>Closed</td></tr>'
            '<tr><td>2026</td><td><a href="/php_sets/uploads/2026/04/Tender.pdf">IT equipment</a></td><td>Tender</td><td>Open</td></tr>'
            '<tr><td>2026</td><td><a href="/php_sets/uploads/2026/05/Audit.pdf">Audit services</a></td><td>International tender</td><td>Open</td></tr></table>'
        )
        links = discover_links(None, source, BeautifulSoup(html, "html.parser"), {})
        self.assertEqual([url for url, _ in links], ["https://rai-see.org/php_sets/uploads/2026/10/Vacancy_PO.pdf", "https://rai-see.org/php_sets/uploads/2026/09/Legal_Expert.pdf"])
        with self.assertRaises(ValueError):
            discover_links(None, source, BeautifulSoup("<p>Maintenance</p>", "html.parser"), {})


TALEO_FTL_PAGE = '<html><body><input type="hidden" id="initialHistory" value="ftlx0!|!jobsearch_processSearchInitialHistory%21%24%21requisitionListInterface!|!listRequisition!|!171111!|!Civilian%20Advisor%20!|!264001!|!Bosnia%20and%20Herzegovina-Sarajevo!|!false!|!05-Nov-2026%2C%201%5C%3A59%5C%3A00%20AM!|!NATO%20Headquarter%20Sarajevo%20%28NHQSa%29!|!NATO%20Grade%20G15!|!Apply!|!Submission%20for%20the%20position%5C%3A%20Civilian%20Advisor%20%20-%20%28Job%20Number%5C%3A%20264001%29!|!false!|!listRequisition.nbElements!|!1"></body></html>'


TALEO_FTL_TWO = '<html><body><input type="hidden" id="initialHistory" value="ftlx0!|!listRequisition!|!Head%20of%20Office%20-%20Legal!|!264001!|!Bosnia%20and%20Herzegovina-Sarajevo!|!05-Nov-2026%2C%201%5C%3A59%5C%3A00%20AM!|!NATO%20Headquarter%20Sarajevo%20%28NHQSa%29!|!Submission%20for%20the%20position%5C%3A%20Head%20of%20Office%20-%20Legal%20-%20%28Job%20Number%5C%3A%20264001%29!|!Logistics%20Officer!|!264002!|!Belgium-Mons!|!06-Nov-2026%2C%201%5C%3A59%5C%3A00%20AM!|!NATO%20Headquarter%20Sarajevo%20%28NHQSa%29!|!Submission%20for%20the%20position%5C%3A%20Logistics%20Officer%20-%20%28Job%20Number%5C%3A%20264002%29!|!listRequisition.nbElements!|!2"></body></html>'


class TaleoFtlAdapterTests(TestCase):
    def test_location_field_decides_not_the_organization_label(self):
        organization = Organization.objects.create(name="NATO HQ Sarajevo", kind="international")
        source = Source.objects.create(organization=organization, adapter="taleoftl", url="https://nato.taleo.net/careersection/2/jobsearch.ftl?lang=en&organization=250305010146")
        evidence = {}
        page = lambda request: httpx.Response(200, text=TALEO_FTL_TWO, headers={"content-type": "text/html"})
        with httpx.Client(transport=httpx.MockTransport(page)) as client:
            links = discover_links(client, source, None, evidence)
        self.assertEqual([title for _, title in links], ["Head of Office - Legal"])
        self.assertIn("Location: Bosnia and Herzegovina-Sarajevo.", evidence[links[0][0]])

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_encoded_list_read_and_closing_day_corrected(self, _):
        organization = Organization.objects.create(name="NATO HQ Sarajevo", kind="international")
        source = Source.objects.create(organization=organization, adapter="taleoftl", url="https://nato.taleo.net/careersection/2/jobsearch.ftl?lang=en&organization=250305010146")
        evidence = {}
        page = lambda request: httpx.Response(200, text=TALEO_FTL_PAGE, headers={"content-type": "text/html"})
        with httpx.Client(transport=httpx.MockTransport(page)) as client:
            links = discover_links(client, source, None, evidence)
        self.assertEqual(links, [("https://nato.taleo.net/careersection/2/jobdetail.ftl?job=264001", "Civilian Advisor")])
        candidate = make_candidate(source, links[0][0], links[0][1], evidence[links[0][0]], None)
        self.assertEqual((candidate.deadline, candidate.city), (date(2026, 11, 4), "Sarajevo"))
        self.assertIn("NATO Grade G15", evidence[links[0][0]])


ILO_FEED = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>ILO</title>
<item><title>Project Manager - P4 (Nairobi, KE)</title><link>https://jobs.ilo.org/job/Nairobi-Project-Manager-P4/1442801033/?feedId=null&amp;utm_source=J2WRSS</link><guid>1</guid><pubDate>Wed, 30 Sep 2026 0:00:00 GMT</pubDate><description>&lt;p&gt;Location: Nairobi Contract type: Fixed Term&lt;/p&gt;</description></item>
<item><title>National Project Officer - Grant Officer - NOA</title><link>https://jobs.ilo.org/job/Sarajevo-National-Project-Officer/1442900033/?utm_source=J2WRSS</link><guid>2</guid><pubDate>Mon, 28 Sep 2026 0:00:00 GMT</pubDate><description>&lt;p&gt;Grade: NOA Application deadline (Midnight, Geneva time): 12 October 2026 Job ID: 13900 Location: Sarajevo Contract type: Fixed Term&lt;/p&gt;</description></item>
</channel></rss>"""


class SuccessFactorsRssTests(TestCase):
    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_feed_items_kept_by_bih_location(self, _):
        organization = Organization.objects.create(name="ILO", kind="international")
        source = Source.objects.create(organization=organization, adapter="sfrss", url="https://jobs.ilo.org/services/rss/job/?locale=en_GB&keywords=")
        evidence = {}
        feed = lambda request: httpx.Response(200, content=ILO_FEED.encode(), headers={"content-type": "application/rss+xml"})
        with httpx.Client(transport=httpx.MockTransport(feed)) as client:
            links = discover_links(client, source, None, evidence)
        self.assertEqual(links, [("https://jobs.ilo.org/job/Sarajevo-National-Project-Officer/1442900033", "National Project Officer - Grant Officer - NOA")])
        reordered = ILO_FEED.replace("National Project Officer - Grant Officer - NOA", "Grant Officer").replace("Location: Sarajevo Contract type", "Location: Sarajevo Job ID: 13900 Contract type")
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=reordered.encode(), headers={"content-type": "application/rss+xml"}))) as client:
            self.assertEqual(len(discover_links(client, source, None, {})), 1, "a BiH location followed by any label is kept")
        candidate = make_candidate(source, links[0][0], links[0][1], evidence[links[0][0]], None)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city, candidate.scope), (date(2026, 9, 28), date(2026, 10, 12), "Sarajevo", "national"))
        self.assertTrue(candidate.eligible and candidate.year_proven)


class LanteriaAdapterTests(TestCase):
    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_embedded_list_filtered_and_listing_title_kept(self, _):
        organization = Organization.objects.create(name="ICMPD", kind="international")
        source = Source.objects.create(organization=organization, adapter="lanteria", url="https://careers.icmpd.org/")
        jobs = [{"id": 1222, "title": "VA26P172V01 Senior Project Manager (IP4)", "locations": ["Lviv"], "startDate": "2026-10-02T00:00:00Z"}, {"id": 1230, "title": "VA26P180V01 Project Management Assistant - LS2", "locations": ["Sarajevo"], "startDate": "2026-09-29T00:00:00Z"}]
        page = lambda request: httpx.Response(200, text=f"<script>var jobOpeningsData = {{ itemsPerPage: 20, jobOpenings: {json.dumps(jobs)} }};</script>", headers={"content-type": "text/html"})
        evidence = {}
        with httpx.Client(transport=httpx.MockTransport(page)) as client:
            links = discover_links(client, source, None, evidence)
        url = "https://careers.icmpd.org/Home/JobOpeningDetails?jobOpeningId=1230"
        self.assertEqual(links, [(url, "VA26P180V01 Project Management Assistant - LS2")])
        detail = BeautifulSoup("<h1>Job Opening Details</h1><p>Closing Date 24/10/2026 Back to Listings VA26P180V01 Project Management Assistant - LS2 Sarajevo</p>", "html.parser")
        candidate = make_candidate(source, url, links[0][1], detail.get_text(" ", strip=True), detail, evidence[url])
        self.assertEqual((candidate.title, candidate.source_published_at, candidate.deadline, candidate.city, candidate.scope), ("VA26P180V01 Project Management Assistant - LS2", date(2026, 9, 29), date(2026, 10, 24), "Sarajevo", "national"))
        self.assertTrue(candidate.eligible)


class CsodAdapterTests(TestCase):
    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 2))
    def test_token_read_and_ba_postings_kept(self, _):
        organization = Organization.objects.create(name="World Bank", kind="international")
        source = Source.objects.create(organization=organization, adapter="csod", url="https://worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup")
        evidence = {}
        with httpx.Client(transport=httpx.MockTransport(csod_site)) as client:
            links = discover_links(client, source, None, evidence)
        self.assertEqual(links, [("https://worldbankgroup.csod.com/ux/ats/careersite/1/home/requisition/38336?c=worldbankgroup", "Operations Analyst")])
        candidate = make_candidate(source, links[0][0], links[0][1], evidence[links[0][0]], None)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 9, 18), date(2026, 10, 9), "Sarajevo"))
        self.assertTrue(candidate.eligible and candidate.year_proven)


@override_settings(SECURE_SSL_REDIRECT=True, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class SslRedirectTests(TestCase):
    def test_health_stays_plain_http_for_container_check(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 301)


class ScrapeCommandTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        self.first = Source.objects.create(organization=organization, url="https://a.example/jobs", adapter="generic", enabled=True)
        self.second = Source.objects.create(organization=organization, url="https://b.example/jobs", adapter="generic", enabled=True)

    def call(self, *args):
        import io
        from django.core.management import call_command
        out, err = io.StringIO(), io.StringIO()
        call_command("scrape_jobs", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_one_crash_does_not_stop_others_or_expiry(self):
        import io
        import logging
        from .ingest import ScrapeRun
        console = next(handler for handler in logging.getLogger("board").handlers if handler.name == "console")
        logged = io.StringIO()
        calls = []
        def ingest(pk):
            calls.append(pk)
            if pk == self.first.pk:
                raise RuntimeError("database hiccup")
            return ScrapeRun(source_id=pk, success=True)
        with patch.object(console, "stream", logged), patch("board.management.commands.scrape_jobs.ingest_source", side_effect=ingest), patch("board.management.commands.scrape_jobs.expire_jobs") as expire:
            out, err = self.call()
        self.assertEqual(sorted(calls), sorted([self.first.pk, self.second.pk]))
        self.assertIn("database hiccup", err)
        self.assertIn(f"Source {self.first.pk}: unexpected scrape error", logged.getvalue())
        self.assertIn("Traceback (most recent call last)", logged.getvalue())
        self.assertIn("RuntimeError: database hiccup", logged.getvalue())
        expire.assert_called_once()

    def test_unknown_source_is_an_error(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self.call("--source", "999")

    def test_overlapping_run_is_skipped(self):
        from .ingest import ingest_source
        from .models import ScrapeRun
        ScrapeRun.objects.create(source=self.first)
        self.assertIsNone(ingest_source(self.first.pk))
        self.assertEqual(self.first.runs.count(), 1)


class EnrichmentTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        source = Source.objects.create(organization=organization, url="https://a.example/jobs")
        self.job = Job.objects.create(source=source, canonical_url="https://a.example/1", title="Driver", content_hash="h1", raw_text="Driver wanted. Duty station: Sarajevo. Applications by 30 November 2026 via https://apply.example/driver")

    def run_import(self, *items):
        import io
        import tempfile
        from pathlib import Path
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "suggestions.jsonl"
            path.write_text("\n".join(json.dumps(item) for item in items), encoding="utf-8")
            err = io.StringIO()
            call_command("import_enrichment", str(path), stdout=io.StringIO(), stderr=err)
        self.job.refresh_from_db()
        return err.getvalue()

    def suggestion(self, proposed, evidence, content_hash="h1"):
        return {"id": self.job.pk, "content_hash": content_hash, "proposed": proposed, "evidence": evidence}

    def test_export_lists_review_jobs(self):
        import io
        from django.core.management import call_command
        out = io.StringIO()
        call_command("export_enrichment", stdout=out)
        row = json.loads(out.getvalue().splitlines()[0])
        self.assertEqual((row["id"], row["content_hash"], row["employer"]), (self.job.pk, "h1", "Embassy"))

    def test_supported_suggestion_applied_and_marked_ai(self):
        self.run_import(self.suggestion({"city": "Sarajevo", "deadline": "2026-11-30", "application_url": "https://apply.example/driver"}, {"city": "Duty station: Sarajevo", "deadline": "Applications by 30 November 2026", "application_url": "via https://apply.example/driver"}))
        self.assertEqual((self.job.city, self.job.deadline, self.job.application_url), ("Sarajevo", date(2026, 11, 30), "https://apply.example/driver"))
        self.assertEqual(self.job.field_evidence["ai_fields"], ["application_url", "city", "deadline"])

    def test_unsupported_suggestions_rejected(self):
        cases = [
            (self.suggestion({"city": "Mostar"}, {"city": "Duty station: Sarajevo"}), "city not in its evidence"),
            (self.suggestion({"deadline": "2026-12-31"}, {"deadline": "Applications by 30 November 2026"}), "deadline not in its evidence"),
            (self.suggestion({"city": "Sarajevo"}, {"city": "Duty station: Banja Luka"}), "unsupported city"),
            (self.suggestion({"city": "Sarajevo"}, {"city": "Duty station: Sarajevo"}, content_hash="old"), "stale source content"),
            (self.suggestion({"title": "Vozač"}, {"title": "Driver wanted"}), "conflicting title"),
        ]
        for item, message in cases:
            self.assertIn(message, self.run_import(item))
        self.assertEqual((self.job.city, self.job.deadline, self.job.title), ("", None, "Driver"))

    def requirement_job(self):
        self.job.raw_text = ("Requirements: Junior college education in Economy or Finance. Minimum of three (3) years of relevant experience. "
                             "Un diplôme universitaire en droit est requis.")
        self.job.save()
        return self.job.raw_text

    def test_requirement_suggestions_applied_and_kept_by_the_rules(self):
        from . import requirements
        self.requirement_job()
        self.run_import(self.suggestion({"education_level": "junior_college", "experience_years": 3, "fields_of_study": ["economics", "law"]},
                                        {"education_level": "Junior college education", "experience_years": "Minimum of three (3) years", "fields_of_study": "Un diplôme universitaire en droit"}))
        self.assertEqual((self.job.education_level, self.job.experience_years, self.job.fields_of_study), ("junior_college", 3, ["economics", "law"]))
        self.assertEqual(self.job.field_evidence["ai_fields"], ["education_level", "experience_years", "fields_of_study"])
        self.job.experience_years = None
        self.job.save()
        requirements.apply(self.job)
        self.assertIsNone(self.job.experience_years, "the rules leave an AI value alone")
        # Where the rules found nothing, the job page shows the quote the value was imported with.
        self.job.experience_years, self.job.requirements = 3, {}
        rows = {label: quote for label, value, quote in requirements.details(self.job)}
        self.assertEqual(rows["Oblast studija"], "Un diplôme universitaire en droit")
        self.assertEqual(rows["Radno iskustvo"], "Minimum of three (3) years")

    def test_unsupported_requirement_suggestions_rejected(self):
        self.requirement_job()
        cases = [
            (self.suggestion({"education_level": "master"}, {"education_level": "Junior college education"}), "education_level not in its evidence"),
            (self.suggestion({"education_level": "diploma"}, {"education_level": "Junior college education"}), "invalid education_level"),
            (self.suggestion({"experience_years": 5}, {"experience_years": "Minimum of three (3) years"}), "experience_years not in its evidence"),
            (self.suggestion({"experience_years": "3"}, {"experience_years": "Minimum of three (3) years"}), "invalid experience_years"),
            (self.suggestion({"fields_of_study": ["finance"]}, {"fields_of_study": "Economy or Finance"}), "invalid fields_of_study"),
            (self.suggestion({"fields_of_study": ["economics"]}, {"fields_of_study": "Economics degree"}), "unsupported fields_of_study"),
        ]
        for item, message in cases:
            self.assertIn(message, self.run_import(item))
        self.job.experience_years = 2
        self.job.save()
        self.assertIn("conflicting experience_years", self.run_import(self.suggestion({"experience_years": 3}, {"experience_years": "Minimum of three (3) years"})))
        self.assertEqual((self.job.education_level, self.job.experience_years, self.job.fields_of_study), ("", 2, []))

    def test_export_of_jobs_missing_requirements(self):
        import io
        from django.core.management import call_command
        complete = Job.objects.create(source=self.job.source, canonical_url="https://a.example/2", title="Analyst", status="published", education_level="bachelor", experience_years=2, fields_of_study=["law"])
        self.job.status = "published"
        self.job.save()
        out = io.StringIO()
        call_command("export_enrichment", "--status", "published", "--missing-requirements", stdout=out)
        rows = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([row["id"] for row in rows], [self.job.pk])
        self.assertEqual(rows[0]["current"]["fields_of_study"], [])
        self.assertNotEqual(complete.pk, self.job.pk)


class VerifySourcesTests(TestCase):
    def test_reports_leads_and_failures_without_writing(self):
        import io
        from django.core.management import call_command
        from .models import ScrapeRun
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        good = Source.objects.create(organization=organization, url="https://a.example/jobs", adapter="generic", enabled=True)
        Source.objects.create(organization=organization, url="https://b.example/jobs", adapter="generic", enabled=True)
        def fake_fetch(client, url):
            if url != good.url:
                raise ValueError("Unusable response: HTTP 403")
            soup = BeautifulSoup('<a href="/jobs/driver">Vacancy: Driver</a>', "html.parser")
            return soup.get_text(), soup
        out = io.StringIO()
        with patch("board.management.commands.verify_sources.fetch", side_effect=fake_fetch):
            call_command("verify_sources", stdout=out)
        self.assertIn("1 leads, 1 in 2026 scope", out.getvalue())
        self.assertIn("FAIL", out.getvalue())
        self.assertIn("1 reachable, 1 failing", out.getvalue())
        self.assertFalse(ScrapeRun.objects.exists() or Job.objects.exists())

    def test_adapter_shape_error_does_not_stop_the_check(self):
        import io
        from django.core.management import call_command
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        Source.objects.create(organization=organization, url="https://a.example/jobs", adapter="generic", enabled=True)
        Source.objects.create(organization=organization, url="https://b.example/jobs", adapter="generic", enabled=True)
        soup = BeautifulSoup("<p>No jobs</p>", "html.parser")
        out = io.StringIO()
        with patch("board.management.commands.verify_sources.fetch", return_value=("", soup)), patch("board.management.commands.verify_sources.discover_links", side_effect=[KeyError("jobId"), []]):
            call_command("verify_sources", stdout=out)
        self.assertIn("1 reachable, 1 failing", out.getvalue())


# The rejected host gets the site's 400 page, which links stylesheets; CI has no collected static manifest.
@override_settings(ALLOWED_HOSTS=["jobs.example.com"], STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ProductionHostTests(TestCase):
    def test_healthcheck_needs_the_public_host_header(self):
        self.assertEqual(self.client.get("/health/", HTTP_HOST="127.0.0.1").status_code, 400)
        self.assertEqual(self.client.get("/health/", HTTP_HOST="jobs.example.com").status_code, 200)


@override_settings(DEBUG=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ProductionLoggingTests(TestCase):
    def test_request_error_reaches_configured_console_with_traceback(self):
        import io
        import logging
        console = next(handler for handler in logging.getLogger("django").handlers if handler.name == "console")
        output = io.StringIO()
        self.client.raise_request_exception = False
        with patch.object(console, "stream", output), patch("board.views.visible_jobs", side_effect=RuntimeError("request logging regression")):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 500)
        logged = output.getvalue()
        self.assertIn("ERROR django.request", logged)
        self.assertIn("Traceback (most recent call last)", logged)
        self.assertIn("RuntimeError: request logging regression", logged)
        self.assertEqual(logged.count("Internal Server Error"), 1)
        self.assertNotIn(b"request logging regression", response.content)


class SchedulerTests(TestCase):
    def test_each_run_cleans_connections_before_scraping(self):
        from .management.commands.run_scraper_schedule import Command
        events = []
        with patch("board.management.commands.run_scraper_schedule.close_old_connections", side_effect=lambda: events.append("cleanup")), patch("board.management.commands.run_scraper_schedule.call_command", side_effect=lambda *args, **kwargs: events.append("scrape")) as scrape:
            command = Command()
            command.run_once(source=7)
            command.run_once()
        self.assertEqual(events, ["cleanup", "scrape", "cleanup", "scrape"])
        self.assertEqual(scrape.call_args_list[0].args, ("scrape_jobs",))
        self.assertEqual(scrape.call_args_list[0].kwargs, {"source": 7})

    def test_failed_run_logs_traceback_and_allows_next_run(self):
        import io
        import logging
        from .management.commands.run_scraper_schedule import Command
        console = next(handler for handler in logging.getLogger("board").handlers if handler.name == "console")
        output = io.StringIO()
        with patch.object(console, "stream", output), patch("board.management.commands.run_scraper_schedule.close_old_connections"), patch("board.management.commands.run_scraper_schedule.call_command", side_effect=[RuntimeError("database unavailable"), None]) as scrape:
            command = Command()
            command.run_once(source=7)
            command.run_once()
        self.assertEqual(scrape.call_count, 2)
        self.assertIn("Scheduled scrape failed (source=7)", output.getvalue())
        self.assertIn("Traceback (most recent call last)", output.getvalue())
        self.assertIn("RuntimeError: database unavailable", output.getvalue())

    def test_cleanup_failure_does_not_stop_future_runs(self):
        from .management.commands.run_scraper_schedule import Command
        with patch("board.management.commands.run_scraper_schedule.close_old_connections", side_effect=[RuntimeError("cleanup failed"), None]), patch("board.management.commands.run_scraper_schedule.call_command") as scrape:
            command = Command()
            with self.assertLogs("board.management.commands.run_scraper_schedule", level="ERROR"):
                command.run_once()
            command.run_once()
        scrape.assert_called_once_with("scrape_jobs")

    def test_next_run_is_six_in_the_morning_local(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from .management.commands.run_scraper_schedule import seconds_until_next_run
        sarajevo = ZoneInfo("Europe/Sarajevo")
        self.assertEqual(seconds_until_next_run(datetime(2026, 10, 2, 5, 30, tzinfo=sarajevo)), 30 * 60)
        self.assertEqual(seconds_until_next_run(datetime(2026, 10, 2, 6, 0, tzinfo=sarajevo)), 24 * 60 * 60)
        self.assertEqual(seconds_until_next_run(datetime(2026, 10, 2, 18, 0, tzinfo=sarajevo)), 12 * 60 * 60)
        # Clocks go back on 25 October 2026 and forward on 28 March 2027.
        self.assertEqual(seconds_until_next_run(datetime(2026, 10, 24, 7, 0, tzinfo=sarajevo)), 24 * 60 * 60)
        self.assertEqual(seconds_until_next_run(datetime(2027, 3, 27, 7, 0, tzinfo=sarajevo)), 22 * 60 * 60)

    def test_start_skips_run_when_scraped_recently_and_clears_lock(self):
        from .management.commands.run_scraper_schedule import Command
        from .management.commands.scrape_jobs import lock_path
        from .models import ScrapeRun
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        ScrapeRun.objects.create(source=Source.objects.create(organization=organization, url="https://a.example/jobs"))
        lock = lock_path()
        self.addCleanup(lock.unlink, missing_ok=True)
        lock.write_text("1")
        with patch("board.management.commands.run_scraper_schedule.close_old_connections"), patch("board.management.commands.run_scraper_schedule.call_command") as scrape, patch("board.management.commands.run_scraper_schedule.time.sleep", side_effect=KeyboardInterrupt), patch("board.management.commands.run_scraper_schedule.signal.signal"):
            with self.assertRaises(KeyboardInterrupt):
                Command().handle()
        scrape.assert_not_called()
        self.assertFalse(lock.exists())

    def test_start_finishes_an_interrupted_run(self):
        from django.utils import timezone
        from .management.commands.run_scraper_schedule import Command
        from .models import ScrapeRun
        organization = Organization.objects.create(name="Embassy", kind="embassy")
        done = Source.objects.create(organization=organization, url="https://a.example/jobs", adapter="generic", enabled=True)
        left = Source.objects.create(organization=organization, url="https://b.example/jobs", adapter="generic", enabled=True)
        ScrapeRun.objects.create(source=done, finished_at=timezone.now())
        killed = Source.objects.create(organization=organization, url="https://c.example/jobs", adapter="generic", enabled=True)
        ScrapeRun.objects.create(source=killed)
        with patch("board.management.commands.run_scraper_schedule.close_old_connections"), patch("board.management.commands.run_scraper_schedule.call_command") as scrape, patch("board.management.commands.run_scraper_schedule.time.sleep", side_effect=KeyboardInterrupt), patch("board.management.commands.run_scraper_schedule.signal.signal"):
            with self.assertRaises(KeyboardInterrupt):
                Command().handle()
        self.assertEqual([call.kwargs for call in scrape.call_args_list], [{"source": left.pk}, {"source": killed.pk}])
        self.assertFalse(ScrapeRun.objects.filter(finished_at__isnull=True).exists())


@skipUnless(connection.vendor == "postgresql", "Requires the disposable PostgreSQL test database")
class SchedulerPostgresTests(TransactionTestCase):
    def test_next_run_recovers_after_database_connection_is_terminated(self):
        import psycopg
        from django.db import OperationalError
        from .management.commands.run_scraper_schedule import Command
        # TestCase's transaction would prevent connection recycling; this test runs in autocommit.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            backend_pid = cursor.fetchone()[0]
        # Connect only to the test runner's database and kill only this test's Django connection.
        with psycopg.connect(**connection.get_connection_params(), autocommit=True) as other:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_terminate_backend(%s, 5000)", (backend_pid,))
                self.assertTrue(cursor.fetchone()[0])
        with self.assertRaises(OperationalError):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        counts = []
        with patch("board.management.commands.run_scraper_schedule.call_command", side_effect=lambda *args, **kwargs: counts.append(Source.objects.count())) as scrape:
            command = Command()
            command.run_once()
            command.run_once()
        self.assertEqual(counts, [0, 0])
        self.assertEqual(scrape.call_count, 2)


class BosnianPluralTests(TestCase):
    def test_count_agreement(self):
        from .text import bs_plural
        self.assertEqual([bs_plural(n, "oglas", "oglasa", "oglasa") + "/" + bs_plural(n, "nije objavljen", "nisu objavljena", "nije objavljeno") for n in (1, 2, 5, 11, 12, 21, 22, 25)],
                         ["oglas/nije objavljen", "oglasa/nisu objavljena", "oglasa/nije objavljeno", "oglasa/nije objavljeno", "oglasa/nije objavljeno", "oglas/nije objavljen", "oglasa/nisu objavljena", "oglasa/nije objavljeno"])
