from django.db import models
from django.utils import timezone
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .requirements import EDUCATION_LEVELS
from .text import fold


class Organization(models.Model):
    TYPE_CHOICES = [("aggregator", _("Agregator poslova")), ("embassy", _("Ambasada")), ("consulate", _("Konzulat")), ("honorary", _("Počasni konzulat")), ("international", _("Međunarodna organizacija")), ("ngo", _("Međunarodna nevladina organizacija")), ("agency", _("Razvojna agencija"))]
    RECRUITMENT_STATUS = [("", "Nije provjeren"), ("not_found", "Izvor nije pronađen"), ("integration", "Čeka integraciju"), ("blocked", "Provjera nije uspjela")]
    name = models.CharField(max_length=240, unique=True)
    # Shown as the employer monogram on job cards ("OSCE", "UNDP", a country code for missions).
    short_name = models.CharField(max_length=8, blank=True)
    kind = models.CharField(max_length=20, choices=TYPE_CHOICES)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    website = models.URLField(max_length=1000, blank=True)
    evidence_url = models.URLField(max_length=1000, blank=True)
    verified_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # Separate recruitment discovery from verified_at (diplomatic presence) and Source.last_success_at (a successful scrape).
    recruitment_status = models.CharField(max_length=20, choices=RECRUITMENT_STATUS, blank=True)
    recruitment_checked_at = models.DateField(null=True, blank=True)
    recruitment_evidence_url = models.URLField(max_length=1000, blank=True)
    recruitment_notes = models.TextField(blank=True)

    def __str__(self):
        return self.name

    @property
    def slug(self):
        return slugify(fold(self.name))[:80].strip("-") or "organizacija"

    def get_absolute_url(self):
        return reverse("organization", args=[self.pk, self.slug])


class Source(models.Model):
    STATUS = [("discovered", "Otkriven"), ("verified", "Provjeren"), ("unsupported", "Čeka integraciju"), ("blocked", "Nedostupan"), ("none", "Izvor nije pronađen"), ("failing", "Greška")]
    ADAPTERS = [("none", "Bez adaptera"), ("eeas", "EEAS"), ("govuk", "GOV.UK"), ("generic", "Strukturirana lista"), ("denmark", "Ambasada Danske"), ("italy", "Ambasada Italije"), ("swiss", "Ambasada Švicarske"), ("osce", "Misija OSCE-a"), ("unct", "UN u BiH"), ("ohr", "OHR"), ("eufor", "EUFOR"), ("unicef", "UNICEF"), ("ebrd", "EBRD"), ("rcc", "RCC"), ("era", "Ambasada SAD (ERA)"), ("japan", "Ambasada Japana"), ("oracle", "Oracle Recruiting (UN agencije)"), ("workday", "Workday (UNHCR)"), ("avature", "Avature (Vijeće Evrope, UNOPS)"), ("uncareers", "UN Sekretarijat (careers.un.org)"), ("csod", "Cornerstone (Svjetska banka)"), ("taleo", "Taleo (WHO)"), ("bamboohr", "BambooHR (ICMP)"), ("rmk", "SuccessFactors (UNESCO)"), ("rai", "RAI"), ("taleoftl", "Taleo, stariji (NATO)"), ("sfrss", "SuccessFactors RSS (ILO)"), ("lanteria", "Lanteria (ICMPD)"), ("turkey", "Turske lokalne objave"), ("spain", "Ambasada Spanije"), ("brazil", "Ambasada Brazila"), ("slovenia", "Slovenija MZEZ"), ("canadales", "Kanada LES"), ("peoplesoft", "PeopleSoft Atom feed (EIB)"), ("sitemap", "Sitemap misije (Njemačka)"), ("wordpress", "WordPress oglasnik (mreza-mira.net)"), ("undpnotices", "UNDP procurement notices (IC)"), ("kemlu", "Portal Kemlu (Indonezija)"), ("reliefweb", "ReliefWeb"), ("impactpool", "Impactpool")]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="sources")
    url = models.URLField(max_length=1000)
    adapter = models.CharField(max_length=20, choices=ADAPTERS, default="none")
    adapter_config = models.JSONField(default=dict, blank=True, help_text="Optional listing URL patterns and link selectors")
    status = models.CharField(max_length=20, choices=STATUS, default="discovered")
    enabled = models.BooleanField(default=False)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "url"], name="unique_org_source")]

    def __str__(self):
        return f"{self.organization}: {self.url}"


class ScrapeRun(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="runs")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(default=False)
    candidates = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)


class SourceDocument(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="documents")
    url = models.URLField(max_length=1000)
    fetched_at = models.DateTimeField(default=timezone.now)
    content_hash = models.CharField(max_length=64)
    text = models.TextField()

    class Meta:
        # The latest snapshot of a page is looked up per candidate in every run and in the job admin.
        indexes = [models.Index(fields=["fetched_at"]), models.Index(fields=["source", "url", "-fetched_at"], name="sourcedoc_latest")]


class Job(models.Model):
    STATUS = [("review", "Na provjeri"), ("published", "Objavljeno"), ("closed", "Zatvoreno")]
    CLOSED_REASON = [("deadline", "Istekao rok"), ("missing", "Nestao sa izvora"), ("stale", "Bez roka, zastario"), ("withdrawn", "Povučen na izvoru"), ("manual", "Zatvoren ručno")]
    TYPE = [("employment", _("Zaposlenje")), ("paid_internship", _("Plaćena praksa")), ("consultancy", _("Individualni konsultantski angažman"))]
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="jobs")
    external_id = models.CharField(max_length=250, blank=True)
    canonical_url = models.URLField(max_length=1000)
    application_url = models.URLField(max_length=1000, blank=True)
    title = models.CharField(max_length=400)
    city = models.CharField(max_length=100, blank=True)
    opportunity_type = models.CharField(max_length=30, choices=TYPE, default="employment")
    scope = models.CharField(max_length=20, choices=[("national", _("Nacionalna pozicija")), ("international", _("Međunarodna pozicija"))], blank=True)
    deadline = models.DateField(null=True, blank=True)
    open_until_filled = models.BooleanField(default=False)
    location_evidence = models.TextField(blank=True)
    eligibility = models.TextField(blank=True)
    source_published_at = models.DateField(null=True, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    missing_scans = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS, default="review")
    # When the job first became public; the employer page lists past jobs only if they were once on the board.
    published_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.CharField(max_length=20, choices=CLOSED_REASON, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    raw_text = models.TextField(blank=True)
    manually_edited_fields = models.JSONField(default=list, blank=True)
    field_evidence = models.JSONField(default=dict, blank=True)
    # Read from raw_text by requirements.extract on every scan; the three filterable values are columns so an admin can correct them.
    requirements = models.JSONField(default=dict, blank=True)
    education_level = models.CharField("minimalno obrazovanje", max_length=20, choices=EDUCATION_LEVELS, blank=True)
    experience_years = models.PositiveSmallIntegerField("godine iskustva", null=True, blank=True)
    fields_of_study = models.JSONField("oblasti studija", default=list, blank=True)
    # Bosnian and English versions written by translation.translate for the text with content_hash; {"disabled": true} opts a job out.
    translations = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "canonical_url"], name="unique_source_job_url")]
        indexes = [models.Index(fields=["status", "first_seen_at"]), models.Index(fields=["deadline"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.status == "published" and not self.published_at:
            self.published_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "published_at"}
        super().save(*args, **kwargs)

    @property
    def employer_name(self):
        return self.field_evidence.get("employer_name") or self.source.organization.name

    @property
    def via(self):
        """The portal a syndicated job came through: an aggregator, or a third-party board (adapter_config.portal_name) filtered to one employer."""
        from .dedup import AGGREGATORS
        if self.source.adapter in AGGREGATORS:
            return self.source.organization.name
        return (self.source.adapter_config or {}).get("portal_name", "")

    @property
    def is_aggregated(self):
        return bool(self.via)

    @property
    def slug(self):
        return slugify(fold(self.title))[:80].strip("-") or "oglas"

    def get_absolute_url(self):
        return reverse("job", args=[self.pk, self.slug])


class Report(models.Model):
    """A problem a visitor reported, about one job or about the site."""
    REASONS = [("expired", _("Oglas je istekao ili je mjesto popunjeno")), ("wrong_info", _("Netačni podaci (rok, lokacija, uslovi)")), ("broken_link", _("Link ne radi")), ("not_bih", _("Posao nije u Bosni i Hercegovini")), ("duplicate", _("Oglas je duplikat")), ("suspicious", _("Sumnjiv ili lažan oglas")), ("missing", _("Nedostaje oglas ili poslodavac")), ("site", _("Greška na stranici")), ("other", _("Drugo"))]
    STATUS = [("new", "Novo"), ("resolved", "Riješeno"), ("dismissed", "Odbačeno")]
    job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    reason = models.CharField("razlog", max_length=20, choices=REASONS)
    message = models.TextField("poruka", max_length=2000, blank=True)
    email = models.EmailField("e-mail za odgovor", blank=True)
    page_url = models.CharField("stranica", max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS, default="new")
    resolved_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField("bilješka", blank=True)
    # A keyed hash of the client address, only for rate limiting; the address itself is not stored.
    client_hash = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["status", "-created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_reason_display()} · {self.job or 'stranica'}"
