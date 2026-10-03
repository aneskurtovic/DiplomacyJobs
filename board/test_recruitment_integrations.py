import json
from datetime import date
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from django.test import TestCase

from board.ingest import ingest_source, make_candidate, rmk_links
from board.models import Job, Organization, Source
from board.recruitment import brazil_links, canada_links, canadian_arrays, slovenia_links, spain_links, turkey_links


def soup(value):
    return BeautifulSoup(value, "html.parser")


def announcement(title, stamp="01.10.2026", publisher="Saraybosna Büyükelçiliği", number=1):
    return f'<a href="/Mission/ShowAnnouncement/{number}"><span class="ks-announcement-header">{title}</span><span class="ks-announcement-from">{publisher}</span><span class="ks-announcement-date">{stamp}</span></a>'


def spanish_block(stamp, role, label, href):
    return f'<h2>Sarajevo, {stamp}</h2><h2>CONVOCATORIA CON LA CATEGORIA DE {role}</h2><p><a href="{href}">{label}</a></p>'


class RecruitmentIntegrationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test mission", city="Sarajevo")

    def source(self, adapter, url, config=None):
        return Source(organization=self.org, adapter=adapter, url=url, adapter_config=config or {"allow_empty": True})

    @patch("board.recruitment.core.fetch")
    def test_turkish_language_local_publisher_year_and_job_filter(self, fetch):
        source = self.source("turkey", "https://saraybosna-be.mfa.gov.tr/Mission/Announcements", {"mission_name": "Saraybosna Büyükelçiliği"})
        html = '<title>Duyurular</title><div id="announcements">' + announcement("Mahalli Kâtip Sınav Duyurusu") + announcement("Mahalli Kâtip", "31.07.2023", number=2) + announcement("Türkçe Yeterlik Sınavı", number=3) + '</div><div id="ministry">' + announcement("Personel alımı", publisher="Ministry", number=4) + '</div>'
        fetch.side_effect = [("", soup(html)), ("", soup('<div id="mainAnnouncements">Büyükelçiliğimiz için mahalli kâtip. Son başvuru tarihi: 20.10.2026</div>'))]
        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, request=req))) as client:
            evidence = {}
            links = turkey_links(client, source, None, evidence)
        self.assertEqual(len(links), 1)
        candidate = make_candidate(source, *links[0], evidence[links[0][0]], None)
        self.assertEqual(candidate.deadline, date(2026, 10, 20))
        self.assertEqual(candidate.source_published_at, date(2026, 10, 1))
        self.assertTrue(candidate.eligible)

    @patch("board.recruitment.core.fetch")
    def test_turkish_missing_structure_is_failure(self, fetch):
        fetch.return_value = ("", soup('<title>Duyurular</title><div id="announcements"></div>'))
        source = self.source("turkey", "https://mission.example/Mission/Announcements")
        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, request=req))) as client:
            with self.assertRaisesMessage(ValueError, "cards missing"):
                turkey_links(client, source, None, {})

    @patch("board.recruitment.core.fetch")
    def test_spanish_results_close_only_the_matching_older_call(self, fetch):
        html = '<div class="single__text">OFERTAS ACTUALES' + spanish_block("13 de agosto del 2026", "AUXILIAR", "Lista definitiva resultado final", "results.pdf") + spanish_block("1 de julio del 2026", "AUXILIAR", "CONVOCATORIA MODIFICADA", "auxiliar.pdf") + spanish_block("1 de octubre del 2026", "CONDUCTOR", "CONVOCATORIA", "driver.pdf") + '</div>'
        source = self.source("spain", "https://www.exteriores.gob.es/Embajadas/sarajevo/es/Embajada/Paginas/Ofertas-de-empleo.aspx")
        fetch.return_value = ("EMBAJADA DE ESPAÑA EN SARAJEVO. Plazo de presentación de solicitudes hasta 20 de octubre de 2026.", None)
        evidence = {}
        links = spain_links(None, source, soup(html), evidence)
        self.assertEqual(len(links), 2)
        candidates = [make_candidate(source, url, title, evidence[url], None) for url, title in links]
        self.assertTrue(next(c for c in candidates if "Auxiliar" in c.title).withdrawn)
        self.assertTrue(next(c for c in candidates if "Conductor" in c.title).eligible)
        self.assertEqual(fetch.call_count, 2)

    @patch("board.recruitment.core.fetch")
    def test_spanish_new_call_same_role_after_final_results_remains_open(self, fetch):
        html = '<div class="single__text">OFERTAS ACTUALES' + spanish_block("13 de agosto del 2026", "AUXILIAR", "Lista definitiva resultado final", "results.pdf") + spanish_block("1 de octubre del 2026", "AUXILIAR", "CONVOCATORIA", "new.pdf") + '</div>'
        source = self.source("spain", "https://www.exteriores.gob.es/Embajadas/sarajevo/list")
        fetch.return_value = ("Location: Sarajevo. Plazo de presentación de solicitudes hasta 20 de octubre de 2026.", None)
        evidence = {}
        url, title = spain_links(None, source, soup(html), evidence)[0]
        self.assertFalse(make_candidate(source, url, title, evidence[url], None).withdrawn)

    def test_spanish_undated_process_fails_instead_of_reporting_empty(self):
        with self.assertRaisesMessage(ValueError, "dates missing"):
            spain_links(None, self.source("spain", "https://www.exteriores.gob.es/list"), soup('<div class="single__text">OFERTAS ACTUALES <a href="call.pdf">Convocatoria</a></div>'), {})

    @patch("board.recruitment.core.fetch")
    def test_spanish_revision_uses_deadline_in_its_dated_inline_notice(self, fetch):
        block = spanish_block("1 de julio del 2026", "AUXILIAR", "CONVOCATORIA MODIFICADA", "call.pdf") + '<ul><li>Nuevo plazo de presentación de solicitudes que finaliza el 13 de julio a las 14:00 horas.</li></ul>'
        source = self.source("spain", "https://www.exteriores.gob.es/Embajadas/sarajevo/list")
        fetch.return_value = ("Sarajevo. No readable deadline in scanned PDF.", None)
        evidence = {}
        url, title = spain_links(None, source, soup('<div class="single__text">OFERTAS ACTUALES' + block + '</div>'), evidence)[0]
        candidate = make_candidate(source, url, title, evidence[url], None)
        self.assertEqual(candidate.deadline, date(2026, 7, 13))

    @patch("board.recruitment.core.fetch")
    def test_brazil_closed_process_and_scanned_pdf_do_not_publish(self, fetch):
        source = self.source("brazil", "https://www.gov.br/mre/2026")
        listing = soup('<div id="content"><a href="/mre/2026/process">Processo seletivo (ENCERRADO / ZATVORENO)</a><a href="/mre/2026/holidays">Feriados</a></div>')
        fetch.side_effect = [("", soup('<div id="content"><a href="/mre/2026/bhs">BHS</a></div>')), ("", soup('<div id="content-core"><a href="/mre/2026/notice.pdf">kompletnu obavijest</a><a href="/mre/2026/final.pdf">rezultati</a></div>')), ("", None)]
        evidence = {}
        url, title = brazil_links(None, source, listing, evidence)[0]
        self.assertTrue(make_candidate(source, url, title, evidence[url], None).withdrawn)
        self.assertEqual(fetch.call_count, 3)

    @patch("board.recruitment.core.fetch")
    def test_brazil_open_scanned_notice_fails_with_ocr_reason(self, fetch):
        source = self.source("brazil", "https://www.gov.br/mre/2026")
        fetch.side_effect = [("", soup('<div id="content"><a href="/mre/2026/bhs">BHS</a></div>')), ("", soup('<div id="content-core"><a href="/mre/2026/notice.pdf">kompletnu obavijest</a></div>')), ("", None)]
        with self.assertRaisesMessage(ValueError, "needs OCR"):
            brazil_links(None, source, soup('<div id="content"><a href="/mre/2026/process">Oglas za posao ABERTO</a></div>'), {})

    def test_slovenia_does_not_import_election_observers_or_foreign_embassy(self):
        source = self.source("slovenia", "https://www.gov.si/zbirke/delovna-mesta/?org%5B0%5D=3745&status=ongoing")
        rows = "".join(f'<tr><td class="td-title"><a href="/zbirke/delovna-mesta/{i}">{title}</a></td><td class="td-publish-date">01.10.2026</td><td class="td-due-date">20.10.2026</td><td class="td-organisation">Ministrstvo za zunanje in evropske zadeve</td></tr>' for i, title in enumerate(["Opazovanje volitev v Bosni in Hercegovini", "Ataše v Veleposlaništvu RS v Pekingu"]))
        with patch("board.recruitment.core.fetch") as fetch:
            self.assertEqual(slovenia_links(None, source, soup('<table class="employment-list-table">' + rows + '</table>'), {}), [])
            fetch.assert_not_called()

    def test_slovenia_pagination_filter_loss_fails(self):
        source = self.source("slovenia", "https://www.gov.si/zbirke/delovna-mesta/?org%5B0%5D=3745&status=ongoing")
        with self.assertRaisesMessage(ValueError, "lost active/employer"):
            slovenia_links(None, source, soup('<table class="employment-list-table"></table><a href="?start=20">Naprej</a>'), {})

    def test_slovenia_empty_shell_is_failure(self):
        with self.assertRaisesMessage(ValueError, "empty listing lacks"):
            slovenia_links(None, self.source("slovenia", "https://www.gov.si/zbirke/delovna-mesta/"), soup('<table class="employment-list-table"></table>'), {})

    def test_uae_missing_count_is_failure_and_startrow_pagination_is_checked(self):
        source = self.source("rmk", "https://www.mofa.gov.ae/en/Careers", {"listing_url": "https://careers.mofa.gov.ae/search/", "pagination": "startrow"})
        with self.assertRaisesMessage(ValueError, "count missing"):
            rmk_links(None, source, soup('<h1>Challenge</h1>'), {})
        row = '<tr class="data-row"><td><a class="jobTitle-link" href="/job/driver/1">Driver</a><span class="jobLocation">Dubai</span></td></tr>'
        with patch("board.ingest.fetch", return_value=("", soup(row))) as fetch:
            with self.assertRaisesMessage(ValueError, "1 of 2"):
                rmk_links(None, source, soup('<span class="paginationLabel">Results 1 of 2</span>' + row), {})
            self.assertIn("startrow=1", fetch.call_args.args[1])

    def test_canadian_javascript_is_parsed_as_data_without_execution(self):
        self.assertEqual(canadian_arrays("e.exports=JSON.parse('[{\"title\":\"Driver\"}]');alert('ignored')"), [[{"title": "Driver"}]])

    def canada_scan(self, jobs, missions):
        source = self.source("canadales", "https://staffing-les.international.gc.ca/en/")
        name, digest = "a" * 40, "b" * 20
        runtime = f'x.u=function(e){{return({{366:"{name}"}}[e]||e)+"-"+{{366:"{digest}"}}[e]+".js"}}'
        bundle = ";".join("e.exports=JSON.parse(" + repr(json.dumps(value)) + ")" for value in [jobs, missions])
        def handle(req):
            if "runtime" in req.url.path:
                return httpx.Response(200, text=runtime, headers={"content-type": "application/javascript"})
            if req.url.path.endswith(".js"):
                return httpx.Response(200, text=bundle, headers={"content-type": "application/javascript"})
            return httpx.Response(200, text='<script src="/webpack-runtime-new.js"></script>')
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            evidence = {}
            links = canada_links(client, source, None, evidence)
        return source, links, evidence

    def canada_job(self, location="Honorary Consulate of Canada in Sarajevo"):
        return {key: [value] for key, value in {"jobCode": "CA-1-en", "Location": location, "mission": "SARAJ", "applyUrl": "https://international8.hiringplatform.ca/processes/1?locale=en", "title": "Driver", "description": "Work authorization in Bosnia required.", "Salary": "Monthly salary", "TermDetails": "Locally engaged staff", "listDate": "Thu, 01 Oct 2026 07:00:00 UTC", "CloseDateYear": "2026", "CloseDateMonth": "October / Octobre", "CloseDateDay": "20"}.items()}

    def test_canadian_duty_station_and_employer_are_independent(self):
        job = self.canada_job("Embassy of Canada to Hungary, Slovenia and Bosnia and Herzegovina")
        source, links, evidence = self.canada_scan([job], [{"SYMBOL": "SARAJ", "country": "Hungary", "city": "Budapest"}])
        self.assertEqual(links, [])

    def test_canadian_local_job_has_dates_salary_and_eligibility(self):
        source, links, evidence = self.canada_scan([self.canada_job()], [{"SYMBOL": "SARAJ", "country": "Bosnia and Herzegovina", "city": "Sarajevo"}])
        self.assertEqual(len(links), 1)
        candidate = make_candidate(source, *links[0], evidence[links[0][0]], None)
        self.assertTrue(candidate.eligible)
        self.assertEqual(candidate.deadline, date(2026, 10, 20))
        self.assertIn("Work authorization", candidate.text)

    def test_canadian_unmatched_local_employer_is_failure(self):
        with self.assertRaisesMessage(ValueError, "does not belong"):
            self.canada_scan([self.canada_job("Embassy of Canada in Sarajevo")], [{"SYMBOL": "SARAJ", "country": "Bosnia and Herzegovina", "city": "Sarajevo"}])

    def test_canadian_missing_job_array_does_not_report_empty(self):
        with self.assertRaisesMessage(ValueError, "arrays missing"):
            self.canada_scan([], [{"SYMBOL": "SARAJ", "country": "Bosnia and Herzegovina", "city": "Sarajevo"}])

    @patch("board.ingest.discover_links", return_value=[])
    @patch("board.ingest.open_client")
    def test_partial_card_feed_retains_job_outside_current_evidence(self, open_client, discover):
        source = Source.objects.create(organization=self.org, url="https://staffing-les.international.gc.ca/en/", adapter="canadales", enabled=True, adapter_config={"allow_empty": True, "partial_listing": True})
        job = Job.objects.create(source=source, canonical_url="https://international8.hiringplatform.ca/processes/old", title="Driver", status="published")
        last_seen = job.last_seen_at
        def unexpected_request(req):
            raise AssertionError("A missing card must not be replaced with an unverified detail fetch")
        open_client.return_value.__enter__.return_value = httpx.Client(transport=httpx.MockTransport(unexpected_request))
        run = ingest_source(source.pk)
        self.assertTrue(run.success, run.error)
        job.refresh_from_db()
        self.assertEqual(job.status, "published")
        self.assertEqual(job.missing_scans, 0)
        self.assertEqual(job.last_seen_at, last_seen)

    @patch("board.ingest.open_client")
    def test_failed_new_adapter_preserves_existing_public_jobs(self, open_client):
        source = Source.objects.create(organization=self.org, url="https://www.exteriores.gob.es/list", adapter="spain", enabled=True, adapter_config={"allow_empty": True})
        job = Job.objects.create(source=source, canonical_url="https://www.exteriores.gob.es/call.pdf", title="Driver", status="published")
        open_client.return_value.__enter__.return_value = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text='<div class="single__text">OFERTAS ACTUALES</div>', headers={"content-type": "text/html"})))
        run = ingest_source(source.pk)
        self.assertFalse(run.success)
        job.refresh_from_db()
        self.assertEqual(job.status, "published")
        self.assertEqual(job.missing_scans, 0)
