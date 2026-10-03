from datetime import date
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from django.test import TestCase

from board.ingest import make_candidate
from board.models import Organization, Source
from board.recruitment import undpnotices_links


def row(nego, title, ref, process, deadline, posted):
    cell = '<div class="vacanciesTable__cell"><div class="vacanciesTable__cell__label">{}</div><span>{}</span></div>'
    cells = [("Title", title), ("Ref No", ref), ("UNDP Office/Country", "UNDP-BIH/BOSNIA AND HERZEGOVINA"), ("Process", process), ("Deadline", f"<nobr>{deadline}<br>09:00 AM (New York time)</nobr>"), ("Posted", f"<nobr>{posted}</nobr>")]
    return f'<a href="view_negotiation.cfm?nego_id={nego}" class="vacanciesTableLink vacanciesTable__row">' + "".join(cell.format(*pair) for pair in cells) + "</a>"


def table(*rows):
    return '<div class="vacanciesTable"><div class="vacanciesTable__header"></div>' + "".join(rows) + "</div>"


class UndpNoticeTests(TestCase):
    def setUp(self):
        self.source = Source(organization=Organization.objects.create(name="UNDP u Bosni i Hercegovini", kind="international"), adapter="undpnotices",
                             url="https://procurement-notices.undp.org/search.cfm", adapter_config={"ref_prefix": "UNDP-BIH", "opportunity_type": "consultancy", "allow_empty": True})

    @patch("board.recruitment.core.fetch")
    def test_open_individual_contractor_notices_kept(self, fetch):
        listing = table(
            row(1, "GTP-Expert for Ex-ante evaluation", "UNDP-BIH-01675", "IC - Individual contractor", "14-Oct-26", "01-Oct-26"),
            row(2, "GTP-RFQ-Supply of vehicles", "UNDP-BIH-01674", "RFQ - Request for quotation", "14-Oct-26", "30-Sep-26"),
            row(3, "MEG3-Consultant for Non-revenue Water", "UNDP-BIH-01660", "IC - Individual contractor", "30-Sep-26", "18-Sep-26"))
        posts = []

        def respond(request):
            posts.append(request.content.decode())
            return httpx.Response(200, text=listing, request=request)
        detail = BeautifulSoup("<main>UNDP-BIH-01675 Introduction Country: Bosnia and Herzegovina Assignment Duration: October 2026 - November 2026</main>", "html.parser")
        fetch.return_value = (detail.get_text(" ", strip=True), detail)
        with patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 3)), httpx.Client(transport=httpx.MockTransport(respond)) as client:
            evidence = {}
            links = undpnotices_links(client, self.source, None, evidence)
            candidate = make_candidate(self.source, *links[0], evidence[links[0][0]], None)
        self.assertEqual(posts, ["cur_notice_id=UNDP-BIH"])
        self.assertEqual(links, [("https://procurement-notices.undp.org/view_negotiation.cfm?nego_id=1", "GTP-Expert for Ex-ante evaluation")])
        self.assertEqual(fetch.call_count, 1)  # Closed and non-IC notices are never opened.
        self.assertEqual((candidate.source_published_at, candidate.deadline, candidate.opportunity_type), (date(2026, 10, 1), date(2026, 10, 14), "consultancy"))
        self.assertTrue(candidate.eligible and candidate.year_proven)

    def test_empty_or_foreign_results_fail(self):
        for body, message in ((table(), "missing or empty"), (table(row(1, "X", "UNDP-SRB-1", "IC - Individual contractor", "14-Oct-26", "01-Oct-26")), "another office")):
            with httpx.Client(transport=httpx.MockTransport(lambda request, body=body: httpx.Response(200, text=body, request=request))) as client, self.assertRaisesMessage(ValueError, message):
                undpnotices_links(client, self.source, None, {})
