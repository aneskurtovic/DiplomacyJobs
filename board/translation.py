"""Bosnian and English versions of job adverts.

The board never shows the raw scraped text: it is one flattened line that often carries site navigation. Instead each public
job can carry a short structured version (title, summary, duties, requirements, how to apply) in both interface languages, so
an advert published only in Italian, Portuguese or English can still be read in Bosnian, and a Bosnian one in English.

The versions are written outside the application, in a local Claude Code session (the translate-jobs skill), from a batch
made by `export_translations` and loaded with `import_translations`. There is no API key or model call in the app. Each version
belongs to one text of the job (Job.content_hash): when the source changes, the old version stops showing until the job is
translated again. Scraped facts (deadline, city, requirements) stay authoritative and are shown separately; the page labels the
translation as automatic and links to the official advert.
"""
import re

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

LANGUAGES = ("bs", "en")
# Interface strings: "translated from <language>".
LANGUAGE_NAMES = {"bs": _("bosanskog"), "en": _("engleskog"), "it": _("italijanskog"), "de": _("njemačkog"), "fr": _("francuskog"), "es": _("španskog"), "pt": _("portugalskog"), "tr": _("turskog"), "sl": _("slovenskog"), "id": _("indonezijskog"), "el": _("grčkog"), "ru": _("ruskog"), "ar": _("arapskog"), "ja": _("japanskog"), "nl": _("holandskog"), "pl": _("poljskog"), "hu": _("mađarskog"), "cs": _("češkog"), "sv": _("švedskog")}

# Frequent short words that identify a language in scraped text. Bosnian, Croatian and Serbian share one list: for this board they are the local language.
STOPWORDS = {
    "en": "the and of to in for with is are will be this that or an on as by from have has should",
    "bs": "i u za na je se od sa kao ili da su koji koja koje biti iz po te ako prijava rok oglas radno iskustvo",
    "it": "il di che per della delle dei con non sono del alla una gli le nel nella al questo essere",
    "de": "der die und das für mit ist nicht von zu den dem des ein eine im auf sich werden oder bei",
    "fr": "le la les des et pour avec est une du dans au aux sur par sont ce qui être ou",
    "es": "el los las del para con una por que y en es se al como más su sus o",
    "pt": "os das dos para com uma não são em ao pela pelo processo seletivo no na do da ou",
    "tr": "ve bir için ile olan bu da de olarak veya en çok gibi daha",
    "sl": "in ki je za na se so pri tudi lahko ter oziroma delovno mesto bo ali",
    "id": "dan yang untuk dengan di ini dari atau akan pada dalam kami adalah",
}
STOPWORD_SETS = {code: set(words.split()) for code, words in STOPWORDS.items()}
SERBIAN_CYRILLIC = re.compile(r"[ђћџјљњЂЋЏЈЉЊ]")


def detect_language(text):
    """The main language of a scraped advert as an ISO 639-1 code ("bs" for Bosnian, Croatian and Serbian), or "" when unclear."""
    if len(re.findall(r"[Ͱ-Ͽ]", text)) > 50:
        return "el"
    if len(re.findall(r"[Ѐ-ӿ]", text)) > 50:
        return "bs" if SERBIAN_CYRILLIC.search(text) else "ru"
    words = re.findall(r"[^\W\d_]+", text.casefold())
    if len(words) < 20:
        return ""
    scores = {code: sum(word in vocabulary for word in words) / len(words) for code, vocabulary in STOPWORD_SETS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 0.04 else ""


FIELDS = {"title": 400, "summary": 2000, "how_to_apply": 1000}
LIST_FIELDS = {"responsibilities": 8, "requirements": 10}


def clean(version):
    """Plain, trimmed strings in the expected shape; the templates escape them. Raises ValueError for a malformed version."""
    if not isinstance(version, dict):
        raise ValueError("version is not an object")
    unknown = set(version) - set(FIELDS) - set(LIST_FIELDS)
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")

    def text(value, limit):
        if not isinstance(value, str):
            raise ValueError("expected a string")
        return re.sub(r"\s+", " ", value).strip()[:limit]

    result = {name: text(version.get(name, ""), limit) for name, limit in FIELDS.items()}
    for name, limit in LIST_FIELDS.items():
        items = version.get(name, [])
        if not isinstance(items, list):
            raise ValueError(f"{name} is not a list")
        result[name] = [item for item in (text(value, 400) for value in items[:limit]) if item]
    if not result["title"]:
        raise ValueError("empty title")
    return result


def store(job, data, translator):
    """Validate one imported translation and attach it to the job's current text. Raises ValueError when it is unusable."""
    if (job.translations or {}).get("disabled"):
        raise ValueError("translation is disabled for this job")
    if data.get("content_hash") != job.content_hash:
        raise ValueError("the job's text changed after export; export it again")
    versions = {code: clean(data.get(code)) for code in LANGUAGES}
    # Contact details are copied, never written: each address and link must come from the advert itself.
    source = (job.raw_text or "").casefold()
    for version in versions.values():
        for value in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|https?://[^\s)\]>\"']+", " ".join([*(version[name] for name in FIELDS), *version["responsibilities"], *version["requirements"]])):
            if value.rstrip(".,;:").casefold() not in source:
                raise ValueError(f"{value} does not appear in the advert")
    source = re.sub(r"[^a-z]", "", str(data.get("source_language", "")).lower())[:3] or (job.requirements or {}).get("language", "")
    job.translations = {"content_hash": job.content_hash, "translator": translator[:100], "translated_at": timezone.now().isoformat(), "source_language": source, **versions}
    job.save(update_fields=["translations"])


def pending(jobs):
    """Jobs whose current text has no translation, skipping jobs an admin excluded."""
    return [job for job in jobs if not (job.translations or {}).get("disabled") and (job.translations or {}).get("content_hash") != job.content_hash]


def current_translation(job, language):
    """The version in the given interface language, when it was made from the job's current text."""
    found = job.translations or {}
    if found.get("disabled") or found.get("content_hash") != job.content_hash or language not in found:
        return None
    source = found.get("source_language", "")
    return {**found[language], "source_language": source, "source_name": LANGUAGE_NAMES.get(source, source), "is_translation": source != language}
