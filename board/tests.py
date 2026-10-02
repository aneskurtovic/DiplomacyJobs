from datetime import date
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from django.test import TestCase

from .ingest import discover_links, eeas_page_links, fetch, make_candidate, unct_page_links
from .models import Organization, Source

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
