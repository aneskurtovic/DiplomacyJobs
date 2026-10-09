from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from board.models import Organization, Source
from board.recruitment import nhqsa_links

PAGE = "https://jfcnaples.nato.int/hqsarajevo/about-sarajevo-/working-in-nhqsa/local-positions.aspx"
HEADER = "<tr><td><b>Job Title</b></td><td>Location</td><td>Grade</td><td>Closing Date</td><td>Application Information</td></tr><tr></tr>"


def page(rows=""):
    return BeautifulSoup(f'<main><table class="default">{HEADER}{rows}</table></main>', "html.parser")


class NhqsaTests(SimpleTestCase):
    def setUp(self):
        self.source = Source(organization=Organization(name="NHQSa", city="Sarajevo"), adapter="nhqsa", url=PAGE)

    def test_row_links_its_pdf_with_listing_evidence(self):
        row = '<tr><td>Public Affairs Assistant</td><td>Camp Butmir</td><td>LCH-4</td><td>25-Oct-2026</td><td><a href="/resources/site795/General/NHS GSP 0030_PUBLIC AFFAIRS ASSISTANT.pdf">Download Here (PDF)</a></td></tr>'
        evidence = {}
        links = nhqsa_links(None, self.source, page(row), evidence)
        url = "https://jfcnaples.nato.int/resources/site795/General/NHS%20GSP%200030_PUBLIC%20AFFAIRS%20ASSISTANT.pdf"
        self.assertEqual(links, [(url, "Public Affairs Assistant")])
        self.assertIn("Closing date 2026-10-25.", evidence[url])
        self.assertIn("Duty station: Camp Butmir, Sarajevo. Grade: LCH-4", evidence[url])

    def test_header_only_table_means_no_vacancies(self):
        self.assertEqual(nhqsa_links(None, self.source, page(), {}), [])

    def test_reshaped_page_fails(self):
        with self.assertRaisesMessage(ValueError, "table missing"):
            nhqsa_links(None, self.source, BeautifulSoup("<main><p>Vacancies</p></main>", "html.parser"), {})
        with self.assertRaisesMessage(ValueError, "row changed shape"):
            nhqsa_links(None, self.source, page("<tr><td>Driver</td><td>Camp Butmir</td><td>LCH-2</td><td>soon</td><td></td></tr>"), {})
