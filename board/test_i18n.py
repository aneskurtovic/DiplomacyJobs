import gettext
import json
import re
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone, translation as i18n

from . import requirements, translation
from .models import Job, Organization, Source
from .test_requirements import LOCAL, UNDP

PLAIN_STATIC = override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
ITALIAN = ("Avviso di assunzione di un impiegato a contratto da adibire ai servizi di assistente amministrativo presso l'Ambasciata d'Italia a Sarajevo. "
           "I candidati devono essere in possesso del diploma di scuola secondaria e della conoscenza della lingua italiana. Le domande devono pervenire entro il 20 ottobre 2026 "
           "all'indirizzo sarajevo.segreteria@esteri.it con la documentazione richiesta per la selezione.")


def version(title, **extra):
    return {"title": title, "summary": "Sažetak.", "responsibilities": ["Zadatak"], "requirements": ["Uslov"], "how_to_apply": "", **extra}


class CatalogueTests(TestCase):
    def test_every_interface_string_is_translated_and_compiled(self):
        po = Path(settings.BASE_DIR, "locale/en/LC_MESSAGES/django.po").read_text(encoding="utf-8")
        def joined(lines):
            return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', lines))
        # Long entries are wrapped over several quoted lines.
        entries = [(joined(msgid), joined(msgstr)) for msgid, msgstr in re.findall(r'^msgid ((?:".*"\n)+)msgstr ((?:".*"\n?)+)', po, re.M)]
        entries = [(msgid, msgstr) for msgid, msgstr in entries if msgid]
        self.assertGreater(len(entries), 200)
        self.assertEqual([msgid for msgid, msgstr in entries if not msgstr], [])
        self.assertNotIn("#, fuzzy", po)
        with open(Path(settings.BASE_DIR, "locale/en/LC_MESSAGES/django.mo"), "rb") as handle:
            compiled = gettext.GNUTranslations(handle)
        stale = [msgid for msgid, msgstr in entries if compiled.gettext(msgid.replace('\\"', '"')) != msgstr.replace('\\"', '"')]
        self.assertEqual(stale, [], "run manage.py compilemessages")


class LanguageDetectionTests(TestCase):
    def test_detects_advert_languages(self):
        self.assertEqual(translation.detect_language(UNDP), "en")
        self.assertEqual(translation.detect_language(LOCAL + " Kandidati koji ispunjavaju uslove trebaju dostaviti prijavu za radno mjesto na adresu ambasade."), "bs")
        self.assertEqual(translation.detect_language(ITALIAN), "it")
        self.assertEqual(translation.detect_language("Short"), "")


def make_job(source, title, text, **fields):
    defaults = {"canonical_url": f"https://employer.test/{abs(hash(title))}", "status": "published", "deadline": timezone.localdate() + timedelta(days=10), "raw_text": text, "content_hash": str(abs(hash(text)))}
    job = Job.objects.create(source=source, title=title, **{**defaults, **fields})
    requirements.apply(job)
    job.save()
    return job


@PLAIN_STATIC
class EnglishInterfaceTests(TestCase):
    def setUp(self):
        # A request leaves its language active in the test thread, and reverse() follows it; start each test in Bosnian.
        i18n.activate(settings.LANGUAGE_CODE)
        self.addCleanup(i18n.activate, settings.LANGUAGE_CODE)
        organization = Organization.objects.create(name="Ambasada Italije", kind="embassy")
        self.source = Source.objects.create(organization=organization, url="https://employer.test/jobs", adapter="generic", enabled=True, status="verified")
        self.job = make_job(self.source, "Project Coordinator", UNDP)

    def test_english_board_and_job_page(self):
        board = self.client.get("/en/")
        self.assertContains(board, '<html lang="en">', html=False)
        self.assertContains(board, "Current jobs")
        self.assertContains(board, "1 result")
        self.assertContains(board, "<li>University degree (bachelor)</li>")
        self.assertContains(board, f'href="/en/jobs/{self.job.pk}/project-coordinator/"')
        page = self.client.get(f"/en/jobs/{self.job.pk}/project-coordinator/")
        self.assertContains(page, "At least 2 years")
        self.assertContains(page, "Report a problem with this job")
        self.assertContains(page, f'action="/en/jobs/{self.job.pk}/report/"')
        self.assertContains(self.client.get("/en/sources/"), "Sources and coverage")

    def test_bosnian_stays_unprefixed_and_both_link_each_other(self):
        board = self.client.get("/", HTTP_ACCEPT_LANGUAGE="en")
        self.assertContains(board, '<html lang="bs">', html=False)
        self.assertContains(board, "Aktuelni oglasi")
        self.assertContains(board, '<link rel="alternate" hreflang="en" href="http://testserver/en/">', html=False)
        self.assertContains(board, 'href="/en/" hreflang="en"', html=False)
        filtered = self.client.get("/en/", {"edu": "master"})
        self.assertContains(filtered, 'href="/?edu=master" hreflang="bs"', html=False)
        self.assertEqual(self.client.get("/en/jobs/%d/" % self.job.pk).status_code, 301)

    def test_report_from_english_page_returns_there(self):
        response = self.client.post(f"/en/jobs/{self.job.pk}/report/", {"reason": "expired"}, follow=True)
        self.assertRedirects(response, f"/en/jobs/{self.job.pk}/project-coordinator/")
        self.assertContains(response, "Your report was received")

    def test_sitemap_lists_both_languages(self):
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(f"<loc>http://testserver/jobs/{self.job.pk}/project-coordinator/</loc>", sitemap)
        self.assertIn(f"<loc>http://testserver/en/jobs/{self.job.pk}/project-coordinator/</loc>", sitemap)
        self.assertIn("<loc>http://testserver/en/sources/</loc>", sitemap)


@PLAIN_STATIC
class TranslationImportTests(TestCase):
    def setUp(self):
        # A request leaves its language active in the test thread, and reverse() follows it; start each test in Bosnian.
        i18n.activate(settings.LANGUAGE_CODE)
        self.addCleanup(i18n.activate, settings.LANGUAGE_CODE)
        organization = Organization.objects.create(name="Ambasada Italije", kind="embassy")
        self.source = Source.objects.create(organization=organization, url="https://employer.test/jobs", adapter="generic", enabled=True, status="verified")
        self.job = make_job(self.source, "Avviso di assunzione", ITALIAN)

    def run_import(self, *items):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as handle:
            handle.write("\n".join(json.dumps(item, ensure_ascii=False) for item in items))
        out, err = StringIO(), StringIO()
        call_command("import_translations", handle.name, stdout=out, stderr=err)
        Path(handle.name).unlink()
        return out.getvalue(), err.getvalue()

    def item(self, **overrides):
        return {"id": self.job.pk, "content_hash": self.job.content_hash, "source_language": "it",
                "bs": version("Oglas za zapošljavanje administrativnog asistenta", how_to_apply="Prijave na sarajevo.segreteria@esteri.it do 20. oktobra 2026."),
                "en": version("Recruitment of an administrative assistant"), **overrides}

    def test_export_lists_pending_public_jobs_only(self):
        make_job(self.source, "Review job", ITALIAN + " review", status="review")
        out = StringIO()
        call_command("export_translations", stdout=out)
        lines = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([line["id"] for line in lines], [self.job.pk])
        self.assertEqual(lines[0]["detected_language"], "it")
        self.assertEqual(lines[0]["source_text"], ITALIAN)

    def test_import_shows_translation_in_each_language(self):
        out, err = self.run_import(self.item())
        self.assertIn("1 imported, 0 rejected", out)
        self.job.refresh_from_db()
        self.assertEqual(self.job.translations["translator"], "claude-code")
        bs = self.client.get(self.job.get_absolute_url())
        self.assertContains(bs, "Automatski prijevod sa italijanskog jezika.")
        self.assertContains(bs, "Oglas za zapošljavanje administrativnog asistenta")
        self.assertContains(bs, "<h3>Zadaci</h3>", html=False)
        en = self.client.get("/en" + self.job.get_absolute_url())
        self.assertContains(en, "Machine translation from Italian.")
        self.assertContains(en, "Recruitment of an administrative assistant")
        self.assertContains(self.client.get("/en/"), '<p class="translated-title" lang="en">', html=False)
        # Nothing is pending any more, until the text changes.
        out = StringIO()
        call_command("export_translations", stdout=out)
        self.assertEqual(out.getvalue(), "")

    def test_changed_source_hides_the_old_translation(self):
        self.run_import(self.item())
        Job.objects.filter(pk=self.job.pk).update(content_hash="changed")
        self.assertNotContains(self.client.get(self.job.get_absolute_url()), "Automatski prijevod")

    def test_rejections(self):
        cases = {
            "the job's text changed": self.item(content_hash="old"),
            "does not appear in the advert": self.item(bs=version("Naslov", how_to_apply="Pišite na evil@example.com")),
            "unknown fields": self.item(en={**version("Title"), "script": "<b>x</b>"}),
            "empty title": self.item(en=version(" ")),
            "expected a string": self.item(bs=version("Naslov", summary=["list"])),
        }
        for message, item in cases.items():
            with self.subTest(message=message):
                out, err = self.run_import(item)
                self.assertIn("0 imported, 1 rejected", out)
                self.assertIn(message, err)
        self.job.refresh_from_db()
        self.assertEqual(self.job.translations, {})

    def test_admin_can_opt_a_job_out(self):
        Job.objects.filter(pk=self.job.pk).update(translations={"disabled": True})
        out, err = self.run_import(self.item())
        self.assertIn("disabled", err)
        out = StringIO()
        call_command("export_translations", stdout=out)
        self.assertEqual(out.getvalue(), "")

    def test_translation_text_is_escaped(self):
        self.run_import(self.item(bs=version("<script>alert(1)</script>")))
        self.assertContains(self.client.get(self.job.get_absolute_url()), "&lt;script&gt;alert(1)&lt;/script&gt;")

