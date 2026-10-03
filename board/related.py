"""Which organization a job belongs to, and which current jobs relate to one job: same employer, or similar work elsewhere."""
import re

from .dedup import employer_key
from .text import fold

# Words that say how or where a post is advertised, not what the work is.
NOISE = {
    "and", "for", "the", "with", "from", "open", "all", "interested", "applicants", "applicant", "candidates", "candidate", "internal", "external",
    "national", "international", "post", "position", "tier", "sarajevo", "mostar", "banja", "luka", "tuzla", "bosnia", "herzegovina", "bih", "fbih",
    "nob", "noc", "noa", "nod", "nationals", "only", "local", "staff", "vacancy", "job", "hiring", "team", "level", "grade", "full", "part", "time",
    "unfpa", "undp", "unicef", "osce", "eufor", "eeas", "rta", "who", "ilo", "iom", "unhcr", "unops", "women",
}
# Job-family words: they agree across very different posts ("Expert", "Assistant"), so they count for little on their own.
ROLE_WORDS = {"expert", "consul", "advise", "assist", "office", "specia", "manage", "coordi", "associ", "analys", "admini", "chief", "head", "senior", "junior", "superv", "lead", "projec"}
CONTENT_WEIGHT, ROLE_WEIGHT, FIELD_WEIGHT = 3, 1, 2
# A suggestion needs a title word about the work in common, plus one more signal. Fields of study alone are too broad ("economics" joins
# a General Services chief and a project manager), and so are job-family words.
SIMILAR_THRESHOLD = 4
RELATED_LIMIT = 3


def employer_organization(job, known):
    """The registry organization that employs the job, also for an aggregator copy; None when the registry does not know the employer."""
    return known.get(employer_key(job.employer_name))


def owner(job, known):
    """The organization whose page lists the job: its employer when known, otherwise the source's organization (the aggregator for an unknown employer)."""
    return employer_organization(job, known) or job.source.organization


def stems(title):
    """Title words without advertising noise, cut to six letters so "Consultants" and "consultant" or "Evaluation" and "evaluator" agree."""
    words = re.findall(r"[a-z]+", fold(title))
    return {word[:6] for word in words if len(word) >= 3 and word not in NOISE}


def similarity(job, other):
    """A rule-based score with the reasons behind it: shared title words, shared fields of study, the same contract type and education level."""
    left, right = stems(job.title), stems(other.title)
    shared = left & right
    content = shared - ROLE_WORDS
    fields = set(job.fields_of_study or []) & set(other.fields_of_study or [])
    score = CONTENT_WEIGHT * len(content) + ROLE_WEIGHT * len(shared & ROLE_WORDS) + FIELD_WEIGHT * min(len(fields), 2)
    if not content:
        return 0
    if job.opportunity_type == other.opportunity_type:
        score += 1
    if job.education_level and job.education_level == other.education_level:
        score += 1
    return score


def same_employer(job, candidates, limit=RELATED_LIMIT):
    """Other current jobs of the job's employer, aggregator copies included, newest first."""
    key = employer_key(job.employer_name)
    rows = [other for other in candidates if other.pk != job.pk and employer_key(other.employer_name) == key]
    return sorted(rows, key=lambda other: (other.first_seen_at, other.pk), reverse=True)[:limit]


def similar(job, candidates, limit=RELATED_LIMIT, threshold=SIMILAR_THRESHOLD):
    """Current jobs of other employers that score at least the threshold, best first; empty when nothing is close enough."""
    key = employer_key(job.employer_name)
    scored = [(similarity(job, other), other) for other in candidates if other.pk != job.pk and employer_key(other.employer_name) != key]
    scored = [(score, other) for score, other in scored if score >= threshold]
    scored.sort(key=lambda item: (-item[0], item[1].deadline is None, item[1].deadline, -item[1].pk))
    return [other for _, other in scored[:limit]]
