"""schema.org JobPosting markup for a current job page, so the job can appear in Google's job search.

Everything in it is also visible on the page: the description is built from the advert version and the requirement rows the page shows, never from the stored source text."""
import json
from datetime import datetime, time

from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

# Google's credential categories for our minimum education levels.
CREDENTIALS = {"secondary": "high school", "junior_college": "associate degree", "bachelor": "bachelor degree", "master": "postgraduate degree", "phd": "postgraduate degree"}
TYPES = {"paid_internship": "INTERN", "consultancy": "CONTRACTOR"}


def description(job, translation, details, terms):
    """The page's advert text and requirement rows as simple HTML."""
    parts = []
    if translation:
        if translation.get("summary"):
            parts.append(f"<p>{escape(translation['summary'])}</p>")
        for heading, key in ((gettext("Zadaci"), "responsibilities"), (gettext("Traži se"), "requirements")):
            if items := translation.get(key):
                parts.append(f"<p><strong>{escape(heading)}</strong></p><ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>")
        if translation.get("how_to_apply"):
            parts.append(f"<p><strong>{escape(gettext('Kako se prijaviti'))}</strong></p><p>{escape(translation['how_to_apply'])}</p>")
    rows = [*details, *terms]
    if rows:
        parts.append("<ul>" + "".join(f"<li>{escape(label)}: {escape(value)}</li>" for label, value, _quote in rows) + "</ul>")
    if job.eligibility:
        parts.append(f"<p>{escape(job.eligibility)}</p>")
    if not parts:
        parts.append(f"<p>{escape(job.title)} – {escape(job.employer_name)}</p>")
    return "".join(parts)


def job_posting(job, url, translation, details, terms):
    """The JSON-LD script element for a current, published job."""
    posted = job.source_published_at or timezone.localdate(job.published_at or job.first_seen_at)
    data = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job.title,
        "description": description(job, translation, details, terms),
        "datePosted": posted.isoformat(),
        "url": url,
        "directApply": False,
        "hiringOrganization": {"@type": "Organization", "name": job.employer_name},
        "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": job.city or "Bosna i Hercegovina", "addressCountry": "BA"}},
    }
    organization = getattr(job, "employer_org", None)
    if organization and organization.website:
        data["hiringOrganization"]["sameAs"] = organization.website
    if job.deadline:
        data["validThrough"] = timezone.make_aware(datetime.combine(job.deadline, time(23, 59))).isoformat()
    found = job.requirements or {}
    if kind := TYPES.get(job.opportunity_type):
        data["employmentType"] = kind
    elif work := found.get("work_time"):
        data["employmentType"] = "FULL_TIME" if work["value"] == "full" else "PART_TIME"
    if found.get("remote", {}).get("value") == "remote":
        data["jobLocationType"] = "TELECOMMUTE"
        data["applicantLocationRequirements"] = {"@type": "Country", "name": "BA"}
    if job.education_level in CREDENTIALS:
        data["educationRequirements"] = {"@type": "EducationalOccupationalCredential", "credentialCategory": CREDENTIALS[job.education_level]}
    if job.experience_years is not None:
        data["experienceRequirements"] = {"@type": "OccupationalExperienceRequirements", "monthsOfExperience": job.experience_years * 12} if job.experience_years else "no requirements"
    text = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(f'<script type="application/ld+json">{text}</script>')
