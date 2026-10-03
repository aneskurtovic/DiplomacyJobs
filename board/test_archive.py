from datetime import date
from io import StringIO
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from django.core.management import call_command
from django.test import TestCase

from board import ingest
from board.ingest import archive_source, past_year, rai_links
from board.models import Job, Organization, Source
from board.recruitment import undpnotices_links, wordpress_links
from board.test_undp_notices import row, table

TODAY = date(2026, 10, 3)


def notice(title, published, deadline, place="Sarajevo, Bosnia and Herzegovina"):
    return f"{title}. Published {published}. Closing date {deadline}. Location: {place}. Individual contractor (consultancy)."


class ArchiveSourceTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="UNDP u Bosni i Hercegovini", kind="international")
        self.source = Source.objects.create(organization=organization, adapter="undpnotices", enabled=True, url="https://procurement-notices.undp.org/search.cfm",
                                            adapter_config={"ref_prefix": "UNDP-BIH", "opportunity_type": "consultancy", "history": {"request_delay": 0}})
        Job.objects.create(source=self.source, canonical_url="https://procurement-notices.undp.org/view_negotiation.cfm?nego_id=4", title="Known", status="published")

    def run_archive(self, year, listing):
        def discover(client, source, soup, evidence):
            evidence.update({url: text for url, _, text in listing})
            return [(url, title) for url, title, _ in listing]
        with patch("board.ingest.discover_links", side_effect=discover), patch("board.ingest.timezone.localdate", return_value=TODAY):
            return archive_source(self.source.pk, year)

    def test_ended_adverts_of_the_year_are_stored_closed(self):
        base = "https://procurement-notices.undp.org/view_negotiation.cfm?nego_id="
        jobs = self.run_archive(2026, [
            (base + "1", "Evaluation Consultant", notice("Evaluation Consultant", "2026-03-02", "2026-03-16")),
            (base + "2", "Open Consultant", notice("Open Consultant", "2026-09-30", "2026-10-20")),
            (base + "3", "Regional Expert", notice("Regional Expert", "2026-02-01", "2026-02-15", place="Remote")),
            (base + "4", "Known", notice("Known", "2026-09-01", "2026-09-15")),
            (base + "5", "Last Year Expert", notice("Last Year Expert", "2025-11-03", "2025-11-17")),
        ])
        self.assertEqual([job.title for job in jobs], ["Evaluation Consultant", "Regional Expert"])
        public, hidden = jobs
        self.assertEqual((public.status, public.closed_reason, public.deadline, public.opportunity_type), ("closed", "archive", date(2026, 3, 16), "consultancy"))
        self.assertIsNotNone(public.published_at)
        self.assertEqual(public.field_evidence["archive_year"], 2026)
        # Without a BiH location it may not be shown; the reason stays for an admin.
        self.assertIsNone(hidden.published_at)
        self.assertIn("Lokacija u BiH nije pronađena", hidden.field_evidence["review_reason"])
        self.assertEqual(Job.objects.get(title="Known").status, "published")
        self.assertEqual((ingest.TARGET_YEAR, ingest.ARCHIVE), (2026, False))

    def test_source_without_history_is_refused(self):
        self.source.adapter_config = {"ref_prefix": "UNDP-BIH"}
        self.source.save()
        with self.assertRaisesMessage(ValueError, "no history settings"):
            archive_source(self.source.pk, 2025)

    def test_command_reports_each_source(self):
        out = StringIO()
        with patch("board.management.commands.scrape_jobs.archive_source", return_value=[Job(published_at=None)]) as archive:
            call_command("scrape_jobs", "--history", "2025", stdout=out)
        archive.assert_called_once_with(self.source.pk, 2025)
        self.assertIn(f"{self.source.pk}: 1 archived, 0 listed on the employer page", out.getvalue())


class ArchiveAdapterTests(TestCase):
    def test_rai_keeps_closed_rows_of_the_year_only_in_archive(self):
        cells = "<tr><td>{}</td><td><a href='/php_sets/uploads/{}/x{}.pdf'>{}</a></td><td>{}</td><td>{}</td></tr>"
        rows = [("2025", "2025", 1, "Project Officer", "Vacancy", "Closed"), ("2025", "2025", 2, "Organisational Expert", "Consultancy", "Closed without selection"),
                ("2025", "2025", 3, "Expert", "Consultancy", "Procurement procedure cancelled"), ("2025", "2025", 4, "Printing", "Tender", "Closed"),
                ("2024", "2024", 5, "Officer", "Vacancy", "Closed")]
        soup = BeautifulSoup("<table><tr><th>Year</th><th>Title</th><th>Type</th><th>Status</th></tr>" + "".join(cells.format(*item) for item in rows) + "</table>", "html.parser")
        source = Source(url="https://rai-see.org/tenders-and-vacancies/", adapter="rai")
        self.assertEqual(rai_links(source, soup), [])
        with past_year(2025):
            self.assertEqual([title for _, title in rai_links(source, soup)], ["Project Officer", "Organisational Expert"])

    @patch("board.recruitment.core.fetch")
    def test_undp_archive_searches_the_year_and_keeps_ended_notices(self, fetch):
        listing = table(row(1, "Ended Consultant", "UNDP-BIH-01001", "IC - Individual contractor", "14-Mar-25", "01-Mar-25"),
                        row(2, "Supplies", "UNDP-BIH-01002", "RFQ - Request for quotation", "14-Mar-25", "01-Mar-25"))
        posts = []

        def respond(request):
            posts.append(request.content.decode())
            return httpx.Response(200, text=listing, request=request)
        detail = BeautifulSoup("<main>UNDP-BIH-01001 Introduction Country: Bosnia and Herzegovina</main>", "html.parser")
        fetch.return_value = (detail.get_text(" ", strip=True), detail)
        source = Source(organization=Organization(name="UNDP"), adapter="undpnotices", url="https://procurement-notices.undp.org/search.cfm", adapter_config={"ref_prefix": "UNDP-BIH"})
        with patch("board.ingest.timezone.localdate", return_value=TODAY), httpx.Client(transport=httpx.MockTransport(respond)) as client:
            self.assertEqual(undpnotices_links(client, source, None, {}), [])
            with past_year(2025):
                links = undpnotices_links(client, source, None, {})
        self.assertEqual(posts, ["cur_notice_id=UNDP-BIH", "cur_notice_id=UNDP-BIH&date_from1=2025-01-01&date_to1=2025-12-31"])
        self.assertEqual([title for _, title in links], ["Ended Consultant"])

    def test_wordpress_archive_reads_one_year_with_search(self):
        params = []

        def respond(request):
            params.append(dict(request.url.params))
            return httpx.Response(200, json=[], headers={"x-wp-total": "0", "x-wp-totalpages": "1"}, request=request)
        source = Source(organization=Organization(name="GIZ"), adapter="wordpress", url="https://www.mreza-mira.net/wp-json/wp/v2/posts",
                        adapter_config={"categories": [9, 1272, 5885], "search": "GIZ"})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client, past_year(2025):
            wordpress_links(client, source, None, {})
        self.assertEqual((params[0]["after"], params[0]["before"], params[0]["search"], params[0]["categories"]), ("2025-01-01T00:00:00", "2026-01-01T00:00:00", "GIZ", "9,1272,5885"))
