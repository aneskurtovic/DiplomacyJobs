from django.db import models
from django.utils import timezone


class Organization(models.Model):
    TYPE_CHOICES = [("embassy", "Ambasada"), ("consulate", "Konzulat"), ("honorary", "Počasni konzulat"), ("international", "Međunarodna organizacija")]
    RECRUITMENT_STATUS = [("", "Nije provjeren"), ("not_found", "Izvor nije pronađen"), ("integration", "Čeka integraciju"), ("blocked", "Provjera nije uspjela")]
    name = models.CharField(max_length=240, unique=True)
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


class Source(models.Model):
    STATUS = [("discovered", "Otkriven"), ("verified", "Provjeren"), ("unsupported", "Čeka integraciju"), ("blocked", "Nedostupan"), ("none", "Izvor nije pronađen"), ("failing", "Greška")]
    ADAPTERS = [("none", "Bez adaptera"), ("eeas", "EEAS"), ("govuk", "GOV.UK"), ("generic", "Strukturirana lista"), ("denmark", "Ambasada Danske"), ("italy", "Ambasada Italije"), ("swiss", "Ambasada Švicarske"), ("osce", "Misija OSCE-a"), ("unct", "UN u BiH"), ("ohr", "OHR"), ("eufor", "EUFOR"), ("unicef", "UNICEF"), ("ebrd", "EBRD"), ("rcc", "RCC"), ("era", "Ambasada SAD (ERA)"), ("japan", "Ambasada Japana"), ("oracle", "Oracle Recruiting (UN agencije)"), ("workday", "Workday (UNHCR)"), ("coe", "Vijeće Evrope"), ("uncareers", "UN Sekretarijat (careers.un.org)"), ("csod", "Cornerstone (Svjetska banka)"), ("taleo", "Taleo (WHO)"), ("bamboohr", "BambooHR (ICMP)"), ("rmk", "SuccessFactors (UNESCO)"), ("rai", "RAI"), ("taleoftl", "Taleo, stariji (NATO)"), ("sfrss", "SuccessFactors RSS (ILO)"), ("lanteria", "Lanteria (ICMPD)"), ("turkey", "Turske lokalne objave"), ("spain", "Ambasada Spanije"), ("brazil", "Ambasada Brazila"), ("slovenia", "Slovenija MZEZ"), ("canadales", "Kanada LES")]
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
    TYPE = [("employment", "Zaposlenje"), ("paid_internship", "Plaćena praksa"), ("consultancy", "Individualni konsultantski angažman")]
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="jobs")
    external_id = models.CharField(max_length=250, blank=True)
    canonical_url = models.URLField(max_length=1000)
    application_url = models.URLField(max_length=1000, blank=True)
    title = models.CharField(max_length=400)
    city = models.CharField(max_length=100, blank=True)
    opportunity_type = models.CharField(max_length=30, choices=TYPE, default="employment")
    scope = models.CharField(max_length=20, choices=[("national", "Nacionalna pozicija"), ("international", "Međunarodna pozicija")], blank=True)
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
    closed_reason = models.CharField(max_length=20, choices=CLOSED_REASON, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    raw_text = models.TextField(blank=True)
    manually_edited_fields = models.JSONField(default=list, blank=True)
    field_evidence = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "canonical_url"], name="unique_source_job_url")]
        indexes = [models.Index(fields=["status", "first_seen_at"]), models.Index(fields=["deadline"])]

    def __str__(self):
        return self.title
