from datetime import date
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.test import TestCase

from .ingest import eeas_page_links, make_candidate
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
