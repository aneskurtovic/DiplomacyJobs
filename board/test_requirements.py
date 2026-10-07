from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from . import requirements
from .models import Job, Organization, Report, Source
from .requirements import extract

OSCE = ("Level of Professional Competence Requirements Furthermore, this level of responsibility requires the following: Education: Second-level university degree degree; "
        "Certified training course in a relevant field desirable. A first-level university degree in combination with two years of additional qualifying experience may be "
        "accepted in lieu of the second-level university degree. Experience: Minimum 6 years (8 years with a relevant first-level degree) of relevant, diversified and "
        "progressively responsible professional experience including at least 3 years at the management level relevant to the actual position. Professional fluency in English "
        "with excellent communication skills; Holding a valid driving license. Desirable: Field experience with the OSCE.")
UNDP = ("Required Skills and Experience Education: Advanced university degree (Master's degree or equivalent) in Law, Social Sciences, International Relations, Human Rights "
        "or any other related field is required; OR A first-level university degree (bachelor's degree) in the areas mentioned above, in combination with an additional two "
        "years of qualifying work experience, will be given due consideration in lieu of the advanced university degree. Experience: Minimum two years (with Master´s degree) or "
        "four years (with Bachelor´s degree) of proven project management experience. Languages: Fluency in English and any official languages of Bosnia and Herzegovina "
        "(Bosnian/Croatian or Serbian) is required.")
ERA = ("Qualifications: Experience : Non-supervisory: Must have a minimum of five (5) years’ experience working as a project engineer at a manufacturing plant, hospital, or a "
       "large university/school system. Supervisory: Must have a minimum of one year experience managing/supervising at least 5 subordinates. Education Requirements: The "
       "completion of a 4-year Bachelor of Science degree, or equivalent, in Electrical Engineering from an accredited university.")
LOCAL = ("Uslovi: VSS – završen pravni ili ekonomski fakultet; najmanje 3 godine radnog iskustva na sličnim poslovima; odlično poznavanje engleskog jezika; "
         "poznavanje njemačkog jezika je prednost; vozačka dozvola B kategorije. Ugovor na period od 12 mjeseci, puno radno vrijeme. Plata: 2.400 KM neto mjesečno.")


class ExtractionTests(TestCase):
    def test_osce_minimums_ignore_alternatives_and_sub_requirements(self):
        found = extract("Chief, General Services (S3)", OSCE)
        self.assertEqual(found["education"]["level"], "bachelor")  # the first-level degree accepted in lieu
        self.assertEqual(found["experience"]["years"], 6)  # not the in-lieu 2, the bracketed 8 or the management 3
        self.assertEqual(found["languages"]["required"], ["en"])
        self.assertTrue(found["driving_license"]["required"])
        self.assertEqual(found["grade"]["text"], "S3")

    def test_undp_fields_degree_alternatives_and_languages(self):
        found = extract("Project Coordinator", UNDP)
        self.assertEqual(found["education"]["levels"], ["bachelor", "master"])
        self.assertEqual(found["experience"]["years"], 2)
        self.assertEqual(set(found["fields"]), {"law", "social", "political", "human_rights"})
        self.assertEqual(found["languages"]["required"], ["en", "bcs"])
        self.assertIn("Fluency in English", found["languages"]["quote"])

    def test_us_embassy_total_experience_is_not_the_supervisory_year(self):
        found = extract("Electrical Engineer Supervisor", ERA)
        self.assertEqual(found["experience"]["years"], 5)
        self.assertEqual(found["education"]["level"], "bachelor")
        self.assertEqual(found["fields"], ["engineering"])

    def test_local_language_advert(self):
        found = extract("Administrativni asistent", LOCAL)
        self.assertEqual(found["education"]["level"], "bachelor")
        self.assertEqual(set(found["fields"]), {"law", "economics"})
        self.assertEqual(found["experience"]["years"], 3)
        self.assertEqual(found["languages"]["required"], ["en"])
        self.assertEqual(found["languages"]["desirable"], ["de"])
        self.assertTrue(found["driving_license"]["required"])
        self.assertEqual(found["work_time"]["value"], "full")
        self.assertEqual(found["duration"]["text"], "12 mjeseci")
        self.assertEqual(found["salary"]["text"], "2.400 KM neto mjesečno")

    def test_secondary_school_is_the_minimum_when_offered(self):
        found = extract("Field Consultant", "Minimum requirements: Education: Secondary education, preferably supplemented by relevant training, or university degree in social sciences; Work Experience: Minimum five years of relevant professional experience in social protection.")
        self.assertEqual(found["education"]["level"], "secondary")
        self.assertEqual(found["experience"]["years"], 5)

    def test_unstated_facts_are_omitted(self):
        found = extract("GEF8-Flora Expert", "Introduction Country: Bosnia and Herzegovina Assignment Duration: October 2026 - December 2026 Proposal should be submitted directly in the portal no later than indicated deadline. Documents must be submitted in English.")
        self.assertEqual(set(found) - {"version", "language"}, {"duration"})
        self.assertEqual(found["duration"]["text"], "October 2026 - December 2026")

    def test_numbers_that_are_not_experience(self):
        text = "Experience in at least three relevant processes in the last five years. The roster is valid for three years. Salary: Not Specified."
        self.assertNotIn("experience", extract("Expert", text))
        self.assertNotIn("salary", extract("Expert", text))

    def test_required_before_an_asset_stays_required(self):
        found = extract("Assistant", "Languages: Fluency in English is required and German would be an advantage.")
        self.assertEqual(found["languages"]["required"], ["en"])
        self.assertEqual(found["languages"]["desirable"], ["de"])

    def test_degree_under_desirable_heading_is_not_the_minimum(self):
        text = ("A. ESSENTIAL QUALIFICATIONS: 1. Professional Experience: Minimum 4 years progressively responsible experience in procurement. "
                "2. Education / Training: Junior college education in Economy or Finance. B. DESIRABLE QUALIFICATIONS: 1. Professional Experience: "
                "Previous experience with SAP. 2. Education / Training: University degree up to 3 years, in Finance or Economics.")
        found = extract("Purchasing Administrator", text)
        self.assertEqual(found["education"]["levels"], ["junior_college"])
        self.assertEqual(found["experience"]["years"], 4)

    def test_junior_college_sits_between_secondary_and_bachelor(self):
        for text in ("Education: Junior college education in Economy or Finance.", "Uslovi: VŠS ekonomskog smjera.",
                     "Uslovi: viša stručna sprema ili VI stepen.", "Obrazovanje: završena viša škola.", "Education: associate degree in accounting."):
            with self.subTest(text=text):
                self.assertEqual(extract("Administrator", text)["education"]["level"], "junior_college")
        found = extract("Administrator", "Uslovi: SSS ili VŠS ekonomskog smjera.")
        self.assertEqual(found["education"]["levels"], ["secondary", "junior_college"])
        self.assertEqual(extract("Analyst", "Education: VSS, fakultet ekonomskog smjera.")["education"]["level"], "bachelor")
        self.assertNotIn("education", extract("Assistant", "Ima više školskih projekata i vi stepenujete prioritete."))

    def test_asset_language_and_eu_citizenship(self):
        found = extract("Head of Communications", "GENERAL CONDITIONS Citizenship – Citizen of a Member State of the European Union (EU) and enjoying full rights as a citizen. Language Skills – The candidates must be fully fluent in written and oral English language. Language - Proficiency in local language(s) will be considered an advantage.")
        self.assertEqual(found["citizenship"]["value"], "eu")
        self.assertEqual(found["languages"]["required"], ["en"])
        self.assertEqual(found["languages"]["desirable"], ["bcs"])


def make_job(source, title="Project Coordinator", text=UNDP, **fields):
    defaults = {"canonical_url": f"https://employer.test/{title.replace(' ', '-')}", "status": "published", "deadline": timezone.localdate() + timedelta(days=10), "city": "Sarajevo", "raw_text": text}
    job = Job.objects.create(source=source, title=title, **{**defaults, **fields})
    requirements.apply(job)
    job.save()
    return job


class ApplyTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="UNDP u Bosni i Hercegovini", kind="international")
        self.source = Source.objects.create(organization=organization, url="https://employer.test/jobs", adapter="generic", enabled=True, status="verified")

    def test_admin_corrections_survive_reextraction(self):
        job = make_job(self.source)
        self.assertEqual((job.education_level, job.experience_years), ("bachelor", 2))
        job.education_level, job.manually_edited_fields = "master", ["education_level"]
        job.save()
        changed = requirements.apply(job)
        self.assertNotIn("education_level", changed)
        self.assertEqual(job.education_level, "master")
        self.assertEqual(job.experience_years, 2)


PLAIN_STATIC = override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})


@PLAIN_STATIC
class JobPageTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="UNDP u Bosni i Hercegovini", kind="international")
        self.source = Source.objects.create(organization=organization, url="https://employer.test/jobs", adapter="generic", enabled=True, status="verified")
        self.job = make_job(self.source)
        self.local = make_job(self.source, title="Administrativni asistent", text=LOCAL)

    def test_card_links_to_the_page_and_shows_tags(self):
        content = self.client.get("/").content.decode()
        self.assertIn(f'href="/jobs/{self.job.pk}/project-coordinator/"', content)
        self.assertIn("<li>Fakultet (bachelor)</li>", content)
        self.assertIn("<li>2+ god. iskustva</li>", content)

    def test_page_shows_requirements_with_quotes(self):
        response = self.client.get(self.job.get_absolute_url())
        self.assertContains(response, "<h1>Project Coordinator</h1>", html=False)
        self.assertContains(response, "Najmanje 2 godine")
        self.assertContains(response, "Pravo")
        self.assertContains(response, "Iz oglasa")
        self.assertContains(response, 'action="/jobs/%d/report/"' % self.job.pk)
        self.assertNotContains(response, 'name="robots"')
        local = self.client.get(self.local.get_absolute_url())
        self.assertContains(local, "2.400 KM neto mjesečno")
        self.assertContains(local, "Njemački (prednost)")

    def test_short_and_wrong_slugs_redirect(self):
        self.assertRedirects(self.client.get(f"/jobs/{self.job.pk}/"), self.job.get_absolute_url(), status_code=301)
        self.assertRedirects(self.client.get(f"/jobs/{self.job.pk}/old-title/"), self.job.get_absolute_url(), status_code=301)

    def test_review_jobs_are_private_and_closed_jobs_are_gone(self):
        self.job.status = "review"
        self.job.save()
        self.assertEqual(self.client.get(self.job.get_absolute_url()).status_code, 404)
        self.job.status, self.job.closed_reason = "closed", "deadline"
        self.job.save()
        gone = self.client.get(self.job.get_absolute_url())
        self.assertEqual(gone.status_code, 410)
        self.assertNotContains(gone, "Project Coordinator", status_code=410)

    def test_expired_published_job_is_marked_and_not_indexed(self):
        self.job.deadline = timezone.localdate() - timedelta(days=1)
        self.job.save()
        response = self.client.get(self.job.get_absolute_url())
        self.assertContains(response, "više nije među aktuelnim")
        self.assertContains(response, '<meta name="robots" content="noindex">', html=False)

    def test_requirement_filters(self):
        def titles(**params):
            return self.client.get("/", params).content.decode()
        self.assertIn("Project Coordinator", titles(edu="bachelor"))
        self.assertNotIn("Project Coordinator", titles(edu="secondary"))
        self.assertNotIn("Project Coordinator", titles(edu="junior_college"))
        self.assertIn("Viša škola", titles())
        self.assertNotIn("Project Coordinator", titles(exp="0"))
        self.assertIn("Administrativni asistent", titles(exp="5"))
        self.assertNotIn("Administrativni asistent", titles(exp="2"))
        by_field = titles(field="human_rights")
        self.assertIn("Project Coordinator", by_field)
        self.assertNotIn("Administrativni asistent", by_field)
        self.assertIn("samo oglase u kojima je taj uslov jasno naveden", by_field)
        self.assertIn('href="/feed/?field=human_rights"', by_field)
        # Unknown values are ignored rather than emptying the board.
        self.assertIn("Project Coordinator", titles(edu="nonsense", field="x"))

    def test_sitemap_and_feed_point_to_job_pages(self):
        self.assertContains(self.client.get("/sitemap.xml"), f"<loc>http://testserver{self.job.get_absolute_url()}</loc>")
        self.assertContains(self.client.get("/feed/"), f"http://testserver{self.job.get_absolute_url()}")


@PLAIN_STATIC
class ReportTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="UNDP u Bosni i Hercegovini", kind="international")
        source = Source.objects.create(organization=organization, url="https://employer.test/jobs", adapter="generic", enabled=True, status="verified")
        self.job = make_job(source)

    def test_job_report_is_saved_and_redirects_with_thanks(self):
        response = self.client.post(f"/jobs/{self.job.pk}/report/", {"reason": "expired", "message": " Popunjeno. ", "email": "a@example.com"}, follow=True)
        self.assertRedirects(response, self.job.get_absolute_url())
        self.assertContains(response, "Prijava je zaprimljena")
        report = Report.objects.get()
        self.assertEqual((report.job, report.reason, report.message, report.status), (self.job, "expired", "Popunjeno.", "new"))
        self.assertEqual(len(report.client_hash), 64)

    def test_site_report_keeps_the_page(self):
        self.assertContains(self.client.get("/report/", {"page": "/sources/"}), 'value="/sources/"')
        response = self.client.post("/report/", {"reason": "missing", "message": "Ambasada X ima oglase.", "page": "/sources/"})
        self.assertRedirects(response, "/sources/")
        self.assertEqual(Report.objects.get().page_url, "/sources/")
        # Only site-relative pages are kept, so a report cannot redirect elsewhere.
        self.client.post("/report/", {"reason": "site", "page": "//evil.example/"})
        self.assertEqual(Report.objects.latest("pk").page_url, "")

    def test_validation_honeypot_and_job_reasons(self):
        self.assertContains(self.client.post(f"/jobs/{self.job.pk}/report/", {"reason": "other"}), "Opišite ukratko problem.")
        self.assertContains(self.client.post(f"/jobs/{self.job.pk}/report/", {"reason": "missing"}), "nije među ponuđenim vrijednostima")
        self.client.post(f"/jobs/{self.job.pk}/report/", {"reason": "expired", "website": "http://spam.example"})
        self.assertFalse(Report.objects.exists())

    def test_rate_limit_per_client_behind_the_proxy(self):
        for _ in range(5):
            self.client.post("/report/", {"reason": "site"}, REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.7")
        blocked = self.client.post("/report/", {"reason": "site"}, REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.7")
        self.assertContains(blocked, "više prijava u kratkom roku")
        # Another visitor behind the same proxy is not affected; a forged first hop does not change the client.
        self.client.post("/report/", {"reason": "site"}, REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.1")
        self.assertContains(self.client.post("/report/", {"reason": "site"}, REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="10.9.9.9, 203.0.113.7"), "više prijava u kratkom roku")
        self.assertEqual(Report.objects.count(), 6)

    def test_reports_only_for_published_jobs(self):
        self.job.status = "review"
        self.job.save()
        self.assertEqual(self.client.post(f"/jobs/{self.job.pk}/report/", {"reason": "expired"}).status_code, 404)
