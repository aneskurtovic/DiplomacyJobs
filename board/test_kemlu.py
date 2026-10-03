from datetime import date
from unittest.mock import patch

import httpx
from django.test import TestCase

from board.ingest import make_candidate
from board.models import Organization, Source
from board.recruitment import kemlu_links

API = "https://backpanel.kemlu.go.id/public-content-service/api/contentMenu"


def post(slug, title, published, detail):
    return {"slug": slug, "title": title, "title_eng": title, "publish_date": f"{published} 00:00:00", "content_detail": detail}


class KemluTests(TestCase):
    def setUp(self):
        config = {"portal": "sarajevo", "sections": {"karir": "", "berita": "career|lowongan"}, "allow_empty": True}
        self.source = Source(organization=Organization.objects.create(name="Embassy of the Republic of Indonesia", kind="embassy"), adapter="kemlu", url=API, adapter_config=config)

    def api_client(self, sections):
        def respond(request):
            section, page = request.url.params.get_list("slug[]")[1], int(request.url.params["page"])
            posts, filtered = sections[section]
            return httpx.Response(200, json={"data": {"meta": {"filtered": filtered}, "publication": posts[(page - 1) * 100:page * 100]}}, request=request)
        return httpx.Client(transport=httpx.MockTransport(respond))

    def test_career_section_kept_and_news_filtered(self):
        sections = {
            "karir": ([post("driver", "Local Staff: Driver", "2026-10-01", "<p>Applications no later than 20 October 2026.</p>")], 1),
            "berita": ([post("fair", "Embassy at the Tešanj fair", "2026-09-23", "<p>Fair</p>"), post("career", "CAREER OPPORTUNITY", "2026-09-30", "<p>Deadline: 15 October 2026</p>")], 2),
        }
        with patch("board.ingest.timezone.localdate", return_value=date(2026, 10, 3)), self.api_client(sections) as client:
            evidence = {}
            links = kemlu_links(client, self.source, None, evidence)
            candidates = [make_candidate(self.source, url, title, evidence[url], None) for url, title in links]
        self.assertEqual([url for url, _ in links], ["https://kemlu.go.id/sarajevo/karir/driver", "https://kemlu.go.id/sarajevo/berita/career"])
        self.assertEqual([(c.deadline, c.city) for c in candidates], [(date(2026, 10, 20), "Sarajevo"), (date(2026, 10, 15), "Sarajevo")])
        self.assertTrue(all(c.eligible and c.year_proven for c in candidates))

    def test_short_section_fails(self):
        with self.api_client({"karir": ([], 3), "berita": ([], 0)}) as client, self.assertRaisesMessage(ValueError, "listed 0 of 3"):
            kemlu_links(client, self.source, None, {})
