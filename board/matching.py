"""Explainable candidate-to-job ranking over the same verified jobs as the public board."""

from dataclasses import dataclass

from django.utils.translation import gettext as _

from .related import stems
from .requirements import LEVEL_RANK
from .translation import current_translation


@dataclass(frozen=True)
class Match:
    job: object
    score: int
    tier: str
    reasons: tuple[str, ...]
    cautions: tuple[str, ...]
    unknowns: tuple[str, ...]


def score_job(job, preferences):
    """Return None only for an explicit must-have conflict."""
    score, reasons, cautions, unknowns = 0, [], [], []
    role = (preferences.get("role") or "").strip()
    if role:
        titles = [job.title]
        titles.extend(found["title"] for language in ("bs", "en")
                      if (found := current_translation(job, language)) and found.get("title"))
        if any(stems(role) & stems(title) for title in titles):
            score += 4
            reasons.append(_("Naziv posla odgovara vašem interesu"))
        else:
            cautions.append(_("Naziv posla ne odgovara unesenom interesu"))

    city = preferences.get("city") or ""
    remote = bool(preferences.get("remote"))
    job_remote = (job.requirements or {}).get("remote", {}).get("value") == "remote"
    city_matches = bool(city and job.city and city.casefold() == job.city.casefold())
    remote_matches = bool(remote and job_remote)
    if (city and preferences.get("must_city") and not city_matches) or (remote and preferences.get("must_remote") and not remote_matches):
        return None
    if city or remote:
        if city_matches or remote_matches:
            score += 3
            reasons.append(_("Odgovara željenoj lokaciji ili radu na daljinu"))
        elif not job.city and not job_remote:
            unknowns.append(_("Poslodavac nije jasno naveo lokaciju ili rad na daljinu"))
        else:
            cautions.append(_("Druga lokacija ili način rada"))

    opportunity_type = preferences.get("type") or ""
    if opportunity_type:
        if job.opportunity_type == opportunity_type:
            score += 2
            reasons.append(_("Odgovara željenoj vrsti angažmana"))
        elif preferences.get("must_type"):
            return None
        else:
            cautions.append(_("Druga vrsta angažmana"))

    field = preferences.get("field") or ""
    if field:
        if field in (job.fields_of_study or []):
            score += 2
            reasons.append(_("Odgovara oblasti studija"))
        elif job.fields_of_study:
            cautions.append(_("Oglas navodi drugu oblast studija"))
        else:
            unknowns.append(_("Poslodavac nije naveo oblast studija"))

    education = preferences.get("education") or ""
    if education in LEVEL_RANK:
        if job.education_level:
            if job.education_level in LEVEL_RANK and LEVEL_RANK[job.education_level] <= LEVEL_RANK[education]:
                score += 1
                reasons.append(_("Navedeni nivo obrazovanja odgovara"))
            else:
                cautions.append(_("Oglas navodi viši nivo obrazovanja"))
        else:
            unknowns.append(_("Poslodavac nije naveo minimalno obrazovanje"))

    experience = preferences.get("experience")
    if experience is not None and experience != "":
        if job.experience_years is None:
            unknowns.append(_("Poslodavac nije naveo minimum iskustva"))
        elif job.experience_years <= int(experience):
            score += 1
            reasons.append(_("Navedeno iskustvo odgovara"))
        else:
            cautions.append(_("Oglas navodi više godina iskustva"))

    languages = set(preferences.get("languages") or [])
    required = set((job.requirements or {}).get("languages", {}).get("required") or [])
    if languages:
        if required:
            if required <= languages:
                score += 1
                reasons.append(_("Navedeni jezici odgovaraju"))
            else:
                cautions.append(_("Provjerite jezičke uslove u oglasu"))
        else:
            unknowns.append(_("Poslodavac nije jasno naveo obavezne jezike"))

    citizenship = (job.requirements or {}).get("citizenship", {}).get("value")
    if citizenship:
        cautions.append(_("Oglas ima uslov državljanstva; provjerite na službenom izvoru"))
    elif preferences.get("work_bih") == "no":
        cautions.append(_("Provjerite pravo na rad prije prijave"))

    tier = "strong" if score >= 3 and not cautions and not unknowns else "possible"
    return Match(job, score, tier, tuple(reasons), tuple(cautions), tuple(unknowns))


def rank_jobs(jobs, preferences, excluded_ids=()):
    excluded_ids = set(excluded_ids)
    matches = [score_job(job, preferences) for job in jobs if job.pk not in excluded_ids]
    matches = [match for match in matches if match is not None]
    return sorted(matches, key=lambda match: (match.tier != "strong", -match.score, -match.job.first_seen_at.timestamp(), -match.job.pk))
