import gzip
from datetime import date
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from django.test import TestCase, override_settings

from board.ingest import discover_links, make_candidate
from board.models import Organization, Source
from board.recruitment import peoplesoft_links, sitemap_links, wordpress_links

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


class WordPressBoardTests(TestCase):
    def test_job_categories_paged_and_employer_titles_kept(self):
        posts = [
            {"id": 1, "date": "2026-10-01T09:00:00", "link": "https://www.mreza-mira.net/vijesti/poslovi/giz-local-intern/", "title": {"rendered": "GIZ: Local Intern"},
             "content": {"rendered": "<p>GIZ Office Sarajevo is looking for a paid intern in Sarajevo. Please send your application documents by 15.10.2026.</p>"}},
            {"id": 2, "date": "2026-10-02T09:00:00", "link": "https://www.mreza-mira.net/vijesti/poslovi/caritas-finance-manager/", "title": {"rendered": "Caritas: Finance Manager"},
             "content": {"rendered": "<p>Sarajevo. Rok: 20.10.2026</p>"}},
            {"id": 3, "date": "2026-09-20T09:00:00", "link": "https://www.mreza-mira.net/vijesti/poslovi/advisor/", "title": {"rendered": "Advisor (m/f/d) &#8211; GIZ Office Sarajevo"},
             "content": {"rendered": "<p>Sarajevo. Trajanje oglasa: 14 dana (ističe 30.10.2026.)</p>"}},
        ]
        seen = []

        def respond(request):
            seen.append(dict(request.url.params))
            page = int(request.url.params["page"])
            return httpx.Response(200, json=posts[:2] if page == 1 else posts[2:], headers={"x-wp-total": "3", "x-wp-totalpages": "2"}, request=request)
        config = {"allow_empty": True, "categories": [9, 1272], "exclude_categories": [5885], "title_pattern": r"^GIZ\b|\bGIZ (?:Office|Ured|ured)\b"}
        source = Source(organization=Organization.objects.create(name="GIZ – Ured u Sarajevu", kind="agency"), adapter="wordpress", url="https://www.mreza-mira.net/wp-json/wp/v2/posts", adapter_config=config)
        with patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 3)), httpx.Client(transport=httpx.MockTransport(respond)) as client:
            evidence = {}
            links = wordpress_links(client, source, None, evidence)
            candidates = [make_candidate(source, url, title, evidence[url], None) for url, title in links]
        self.assertEqual((seen[0]["categories"], seen[0]["categories_exclude"], seen[0]["after"], len(seen)), ("9,1272", "5885", "2026-01-01T00:00:00", 2))
        self.assertEqual([title for _, title in links], ["GIZ: Local Intern", "Advisor (m/f/d) – GIZ Office Sarajevo"])
        self.assertEqual([(c.deadline, c.source_published_at, c.city, c.opportunity_type) for c in candidates],
                         [(date(2026, 10, 15), date(2026, 10, 1), "Sarajevo", "paid_internship"), (date(2026, 10, 30), date(2026, 9, 20), "Sarajevo", "employment")])
        self.assertTrue(all(c.eligible and c.year_proven for c in candidates))

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_board_names_the_portal(self):
        from django.utils import timezone
        from board.models import Job
        organization = Organization.objects.create(name="GIZ – Ured u Sarajevu", kind="agency")
        source = Source.objects.create(organization=organization, adapter="wordpress", enabled=True, status="verified", url="https://www.mreza-mira.net/wp-json/wp/v2/posts", adapter_config={"portal_name": "mreza-mira.net"})
        job = Job.objects.create(source=source, canonical_url="https://www.mreza-mira.net/vijesti/poslovi/giz-local-intern", title="GIZ: Local Intern", status="published", deadline=timezone.localdate())
        self.assertEqual((job.via, job.is_aggregated), ("mreza-mira.net", True))
        page = self.client.get("/").content.decode()
        self.assertIn("putem mreza-mira.net", page)
        self.assertIn("Oglas / prijava", page)
        self.assertNotIn("Službeni oglas<", page)

    def test_short_listing_fails(self):
        source = Source(organization=Organization.objects.create(name="GIZ", kind="agency"), adapter="wordpress", url="https://www.mreza-mira.net/wp-json/wp/v2/posts", adapter_config={"categories": [9], "title_pattern": "GIZ"})
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[], headers={"x-wp-total": "5", "x-wp-totalpages": "1"}, request=request))
        with httpx.Client(transport=transport) as client, self.assertRaisesMessage(ValueError, "listed 0 of 5"):
            wordpress_links(client, source, None, {})


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
