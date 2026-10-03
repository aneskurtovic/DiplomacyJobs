import gzip
from datetime import date
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from django.test import TestCase

from board.ingest import discover_links, make_candidate
from board.models import Organization, Source
from board.recruitment import peoplesoft_links, sitemap_links

EIB_FEED = "https://erecruitment.eib.org/PSIGW/HttpListeningConnector/feeds/RealtimeQueryFeed?FEED_ID=ADMN_BEI_HRS_JOB_POSTING_RSS_1&S=P"


def eib_entry(number, title, body, published="2026-09-30"):
    content = f"&lt;table&gt;&lt;tr&gt;&lt;td&gt;Job ID:&lt;/td&gt;&lt;td&gt;{number}&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;&lt;p&gt;{body}&lt;/p&gt;"
    return (f'<entry><title type="html">{title} (Entity: EIB - Job ID: {number})</title><published>{published}T10:00:00.000Z</published>'
            f'<link href="https://erecruitment.eib.org/psc/hr/EIBJOBS/CAREERS/c/HRS_HRAM_FL.HRS_CG_SEARCH_FL.GBL?Page=HRS_APP_JBPST_FL&amp;JobOpeningId={number}&amp;PostingSeq=1" rel="alternate"/>'
            f'<content type="html">{content}</content></entry>')


def eib_feed(*entries, complete=True):
    marker = "<fh:complete/>" if complete else ""
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:fh="http://purl.org/syndication/history/1.0">{marker}{"".join(entries)}</feed>'


def diplo_article(heading, stamp):
    return f'<html><body><main><header><h1 class="heading__title"><span>{heading}</span></h1></header><div>{stamp} - Članak</div><div>Ambasada traži saradnika. Rok za prijavu: 20.10.2026</div></main></body></html>'


class PeopleSoftFeedTests(TestCase):
    def setUp(self):
        self.source = Source(organization=Organization.objects.create(name="EIB", city="Sarajevo"), adapter="peoplesoft", url=EIB_FEED, adapter_config={"allow_empty": True, "active_undated_listing": True})

    def feed_client(self, body):
        return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=body, headers={"content-type": "application/atom+xml"}, request=req)))

    def test_bih_entries_kept_and_stated_deadline_read(self):
        feed = eib_feed(
            eib_entry(1, "Officer - based in Luxembourg", "This position is based at our Luxembourg headquarters. Deadline: Thursday 22nd October 2026"),
            eib_entry(2, "Local Office Assistant", "Deadline: Friday 16th October 2026. This position is based in Sarajevo, Bosnia and Herzegovina. The Western Balkans team works with Luxembourg."),
            eib_entry(3, "Loan Officer - based in Sarajevo", "Open until filled."))
        with patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 3)), self.feed_client(feed) as client:
            evidence = {}
            links = peoplesoft_links(client, self.source, None, evidence)
            self.assertEqual([title for _, title in links], ["Local Office Assistant", "Loan Officer - based in Sarajevo"])
            stated, undated = (make_candidate(self.source, url, title, evidence[url], None) for url, title in links)
        self.assertEqual((stated.deadline, stated.source_published_at, stated.city), (date(2026, 10, 16), date(2026, 9, 30), "Sarajevo"))
        self.assertTrue(stated.eligible and stated.year_proven)
        # No stated deadline: open until filled, kept because the feed is a complete active list.
        self.assertIsNone(undated.deadline)
        self.assertTrue(undated.eligible)

    def test_feed_must_declare_itself_complete(self):
        with self.feed_client(eib_feed(complete=False)) as client, self.assertRaisesMessage(ValueError, "complete Atom feed"):
            peoplesoft_links(client, self.source, None, {})


class SitemapTests(TestCase):
    @patch("board.recruitment.core.fetch")
    def test_new_articles_read_and_job_adverts_kept(self, fetch):
        index = '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://sarajewo.diplo.de/sitemap1.xml.gz</loc></sitemap></sitemapindex>'
        paths = ("2546090-2546090", "2777288-2777288", "2803460-2803460", "service/visa")
        pages = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>https://sarajewo.diplo.de/ba-sh/{path}</loc></url>" for path in paths) + "</urlset>"

        def respond(request):
            if request.url.path.endswith(".gz"):
                return httpx.Response(200, content=gzip.compress(pages.encode()), request=request)
            return httpx.Response(200, text=index, request=request)

        def article(client, url):
            heading = ("Prodaja diplomatskog vozila", "09.07.2026") if "2777288" in url else ("Oglas za posao", "01.10.2026")
            page = BeautifulSoup(diplo_article(*heading), "html.parser")
            return page.get_text(" ", strip=True), page
        fetch.side_effect = article
        config = {"allow_empty": True, "path_prefix": "/ba-sh/", "min_article_id": 2700000, "title_pattern": "oglas za posao", "employer_label": "Ambasada Njemačke"}
        source = Source(organization=Organization.objects.create(name="Germany", city="Sarajevo"), adapter="sitemap", url="https://sarajewo.diplo.de/sitemap_index.xml", adapter_config=config)
        with patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 3)), httpx.Client(transport=httpx.MockTransport(respond)) as client:
            evidence = {}
            links = sitemap_links(client, source, None, evidence)
            self.assertEqual(links, [("https://sarajewo.diplo.de/ba-sh/2803460-2803460", "Oglas za posao — Ambasada Njemačke")])
            # The 2022 article is below the floor and is never fetched.
            self.assertEqual(fetch.call_count, 2)
            candidate = make_candidate(source, *links[0], evidence[links[0][0]], None)
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.city), (date(2026, 10, 1), date(2026, 10, 20), "Sarajevo"))
        self.assertTrue(candidate.eligible and candidate.year_proven)


class UnopsAvatureTests(TestCase):
    def test_contract_markers_are_case_sensitive(self):
        from board.ingest import recruitment_scope
        self.assertEqual(recruitment_scope("Project Associate", "Contract Type: ICA - LICA - Support"), "national")
        self.assertEqual(recruitment_scope("Adviser", "Contract Level: IICA 2"), "international")
        # "lica" is a common Bosnian word ("pravna lica"), not a contract type.
        self.assertEqual(recruitment_scope("Oglas", "Pravna lica i fizička lica mogu se prijaviti"), "")

    @patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 3))
    def test_unops_fields_and_station_class(self, _):
        source = Source.objects.create(organization=Organization.objects.create(name="UNOPS", kind="international"), adapter="avature", url="https://careers.unops.org/careersmarketplace/SearchJobs")
        card = '<article class="article article--result"><h3><a href="https://careers.unops.org/careersmarketplace/JobDetail/Project-Associate/{}">Project Associate</a></h3><span class="list-item-Duty Station">{}</span></article>'
        links = discover_links(None, source, BeautifulSoup("2 results" + card.format(4700, "Banjul") + card.format(4701, "Sarajevo"), "html.parser"))
        self.assertEqual(links, [("https://careers.unops.org/careersmarketplace/JobDetail/Project-Associate/4701", "Project Associate")])
        field = '<div class="article__content__view__field"><div class="article__content__view__field__label">{}</div><div class="article__content__view__field__value">{}</div></div>'
        pairs = [("Position Title", "Project Associate"), ("Duty Station(s)", "Sarajevo"), ("Contract Type", "ICA - LICA - Support"), ("Posting Start Date", "01-Oct-2026"), ("Posting End Date", "15-Oct-2026")]
        detail = BeautifulSoup("<h1>UNOPS</h1>" + "".join(field.format(*pair) for pair in pairs), "html.parser")
        candidate = make_candidate(source, links[0][0], links[0][1], detail.get_text(" ", strip=True), detail)
        self.assertEqual((candidate.title, candidate.city, candidate.source_published_at, candidate.deadline, candidate.scope), ("Project Associate", "Sarajevo", date(2026, 10, 1), date(2026, 10, 15), "national"))
        self.assertTrue(candidate.eligible and candidate.year_proven)
