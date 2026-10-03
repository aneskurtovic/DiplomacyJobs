"""Requirements stated in a vacancy text: education, field of study, years of experience, languages and other recurring terms.

Rule-based and conservative. Each fact keeps the short quote it was read from, so the public page can show where it came from
and an admin can check it. A fact that is not clearly stated is left out rather than guessed. Scraped text is flattened to
one line, so sentences, bullets and labels such as "Experience:" are the only structure available.
"""
import re

from django.utils.translation import gettext, gettext_lazy as _

from .text import plural

VERSION = 3

EDUCATION_LEVELS = [("secondary", _("Srednja škola")), ("bachelor", _("Fakultet (bachelor)")), ("master", _("Master")), ("phd", _("Doktorat"))]
LEVEL_RANK = {value: rank for rank, (value, _) in enumerate(EDUCATION_LEVELS)}

FIELDS = [
    ("law", _("Pravo"), r"\blaw\b|\blegal (?:studies|sciences?)\b|\bjurisprudence|\bLL\.?M\b|\bpravn\w+|\bpravo\b"),
    ("economics", _("Ekonomija, finansije i biznis"), r"\beconomics?\b|\bfinanc\w*|\baccount(?:ing|ancy)\b|\bbusiness\b|\bcommerce\b|\bMBA\b|\bekonom\w+|\bfinansij\w+|\bfinancij\w+|\bračunovod\w+"),
    ("public_admin", _("Javna uprava i menadžment"), r"\bpublic (?:administration|policy|management|affairs)\b|\bmanagement (?:studies|sciences?)\b|\badministrative sciences?\b|\bjavn\w* uprav\w*|\bjavn\w* politik\w*|\bmenadžment\w*"),
    ("political", _("Političke nauke i međunarodni odnosi"), r"\bpolitical sciences?\b|\binternational (?:relations|affairs|studies)\b|\bdiplomacy\b|\beuropean (?:studies|integration)\b|\bpolit\w* nau\w*|\bpolitolog\w*|\bmeđunarodn\w* odnos\w*|\bdiplomatij\w*"),
    ("social", _("Društvene nauke"), r"\bsocial sciences?\b|\bsociology\b|\bpsychology\b|\bsocial (?:work|policy)\b|\banthropology\b|\bdruštven\w* nau\w*|\bsociolog\w*|\bpsiholog\w*|\bsocijaln\w* rad\w*"),
    ("human_rights", _("Ljudska prava i rodne studije"), r"\bhuman rights\b|\bgender\b|\bljudsk\w* prav\w*|\brodn\w* studij\w*"),
    ("engineering", _("Inženjerstvo i arhitektura"), r"\bengineering\b|\barchitecture\b|\binženjer\w*|\bgrađevin\w*|\belektrotehn\w*|\bmašin\w*|\barhitekt\w*"),
    ("it", _("Informatika i IT"), r"\bcomputer sciences?\b|\binformation (?:technology|systems)\b|\binformatics\b|\bsoftware\b|\btelecommunications?\b|\binformati\w+|\bračunarst\w*"),
    ("statistics", _("Statistika i matematika"), r"\bstatistics?\b|\bmathematics\b|\bdemography\b|\bdata science\b|\bstatisti\w+|\bmatemati\w+"),
    ("communications", _("Komunikacije i novinarstvo"), r"\bcommunications?\b|\bjournalism\b|\bmedia\b|\bpublic relations\b|\bmarketing\b|\bnovinar\w*|\bkomunikolog\w*|\bkomunikacij\w*"),
    ("languages", _("Jezici i prevođenje"), r"\blinguistics?\b|\bphilology\b|\btranslation\b|\binterpret(?:ing|ation)\b|\bliterature\b|\bfilolog\w*|\bprevođ\w*|\banglist\w*|\bgermanist\w*"),
    ("health", _("Medicina i zdravstvo"), r"\bmedicine\b|\bmedical\b|\bpublic health\b|\bhealth\b|\bnursing\b|\bpharmac\w+|\bmedicin\w+|\bzdravstv\w*"),
    ("environment", _("Okoliš, poljoprivreda i prirodne nauke"), r"\benvironment\w*|\becology\b|\bbiology\b|\bforestry\b|\bagricultur\w*|\bnatural sciences?\b|\bclimate\b|\bgeography\b|\bchemistry\b|\bokoliš\w*|\bšumarst\w*|\bpoljoprivred\w*|\bbiolog\w*|\bekolog\w*"),
    ("pedagogy", _("Pedagogija i obrazovanje"), r"\beducation(?:al)? sciences?\b|\bpedagog\w*|\bteaching\b"),
    ("security", _("Sigurnost i kriminologija"), r"\bsecurity studies\b|\bmilitary\b|\bcriminology\b|\bkriminal\w*|\bsigurnosn\w* studij\w*"),
    ("logistics", _("Logistika"), r"\blogistics?\b|\bsupply chain\b|\blogisti\w+"),
]
FIELD_LABELS = {slug: label for slug, label, pattern in FIELDS}

LANGUAGES = [
    ("en", _("Engleski"), r"\benglish\b|\bengle\w*"),
    ("bcs", _("Bosanski/hrvatski/srpski"), r"\bbosnian\b|\bcroatian\b|\bserbian\b|\blocal languages?\b|\bnational languages?\b|\bofficial languages? of (?:bosnia|bih)|\bB/C/S\b|\bBCS\b|\bbosansk\w*|\bhrvatsk\w* jezik\w*|\bsrpsk\w* jezik\w*|\blokaln\w* jezik\w*|\bjezik\w* naroda\b"),
    ("de", _("Njemački"), r"\bgerman\b|\bnjemač\w*"),
    ("fr", _("Francuski"), r"\bfrench\b|\bfrancusk\w*"),
    ("it", _("Italijanski"), r"\bitalian\b|\btalijansk\w*|\bitalijansk\w*"),
    ("es", _("Španski"), r"\bspanish\b|\bšpansk\w*|\bšpanjolsk\w*"),
    ("tr", _("Turski"), r"\bturkish\b|\bturs\w* jezik\w*"),
    ("ru", _("Ruski"), r"\brussian\b|\brusk\w* jezik\w*"),
    ("ar", _("Arapski"), r"\barabic\b|\barapsk\w*"),
]
LANGUAGE_LABELS = {code: label for code, label, pattern in LANGUAGES}

WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15,
                "jedna": 1, "jednu": 1, "jedne": 1, "dvije": 2, "dve": 2, "dva": 2, "tri": 3, "četiri": 4, "pet": 5, "šest": 6, "sedam": 7, "osam": 8, "devet": 9, "deset": 10}
NUMBER = r"(\d{1,2}|" + "|".join(WORD_NUMBERS) + r")"

# Phrases that mark a passage as being about formal education.
EDUCATION_CUE = re.compile(r"\b(?:education|degree|diploma|qualification|graduate|university|bachelor|master|ph\.?\s?d|obrazovanj\w*|fakultet\w*|diplom\w*|sprem\w*|studij\w*|školsk\w*)\b", re.I)
LEVEL_PATTERNS = {
    "phd": re.compile(r"\bph\.?\s?d\b|\bdoctora(?:te|l)\b|\bdoktor\w*", re.I),
    "master": re.compile(r"\bmaster\w*|\badvanced (?:university )?degree|\bsecond[- ]level (?:university )?degree|\bpost-?graduate|\bMSc\b|\bLL\.?M\b|\bMBA\b|\bmagist\w*|\bVII[/ ]?1\b", re.I),
    "bachelor": re.compile(r"\bbachelor\w*|\bfirst[- ]level (?:university )?degree|\b1st level (?:university )?degree|\buniversity (?:degree|education|diploma)|\bhigher education\b|\bacademic (?:qualification|degree)|\bundergraduate|\b(?:college|university|academic) degree|\bdegree in\b|['’]s degree|\bBSc\b|\bfakultet\w*|\bVSS\b|\bvisok\w* (?:stručn\w* sprem\w*|obrazovanj\w*)|\bVŠS\b|\bviš\w* stručn\w* sprem\w*", re.I),
    "secondary": re.compile(r"\bsecondary (?:school|education)|\bhigh[- ]school\b|\bsrednj\w* (?:stručn\w* sprem\w*|škol\w*|obrazovanj\w*)|\bSSS\b|\bKV\b", re.I),
}
EXPERIENCE_CUE = re.compile(r"\bexperience\w*|\biskustv\w*|\bstaž\w*", re.I)
YEARS = re.compile(NUMBER + r"(?:\s*\(\d{1,2}\))?\s*\+?\s*(?:full\s+)?(?:years?|yrs?|godin\w*)(?:['’]s?)?", re.I)
# A number that counts something other than the required total experience.
YEARS_NOT_REQUIREMENT = re.compile(r"(?:\blast|\bpast|\bvalid for|\bperiod of|\bmaximum|\bup to|\bwithin|\bduration|\bincluding(?: at least)?|\bof which(?: at least)?|\bod čega(?: najmanje)?|\buključujući|(?<!non-)(?<!non )\bsupervisory:?(?: must have)?(?: a)?(?: minimum of)?|\bin combination with(?: an?)?(?: additional)?|\bplus(?: an?)?(?: additional)?|\badditional|\bposljednjih|\bunder|\bover the|\bfor a period of|\bevery|\bonce in)\s*$", re.I)
YEARS_SUB_REQUIREMENT = re.compile(r"^\s*(?:\)|of )?\s*(?:experience\s+)?(?:(?:of )?additional|(?:at (?:the |a )?|of |in )?(?:management|managerial|senior|supervisory)[- ]level|at (?:the )?(?:management|managerial|senior|supervisory)|of (?:management|managerial|supervisory) experience|(?:as|in) a (?:manager|supervisor|position similar)|managing|supervising|na rukovodn)", re.I)
NO_EXPERIENCE = re.compile(r"\bno (?:prior |previous |work |professional )*experience (?:is )?(?:required|needed|necessary)\b|\bbez (?:radnog )?iskustva\b|\bnije potrebno (?:radno )?iskustvo\b", re.I)
LANGUAGE_CUE = re.compile(r"\blanguages?\b|\bfluen\w*|\bproficien\w*|\bcommand of\b|\bspeaker\b|\bspoken\b|\bwritten\b|\bSLP\b|\bjezi\w*|\bpoznavanj\w*|\bznanj\w*", re.I)
ASSET = re.compile(r"\b(?:asset|advantage|desirable|desired|preferred|preferably|plus|optional|would be|an added|prednost\w*|poželjn\w*)\b", re.I)
DRIVING = re.compile(r"\bdriv(?:ing|er['’]?s?) licen[cs]e\b|\bdriving permit\b|\bvozačk\w* dozvol\w*", re.I)
CITIZENSHIP_BIH = re.compile(r"\b(?:must be|only|are) (?:citizens|nationals) of (?:the country|bosnia)|\bnationals (?:or|and) (?:permanent )?(?:legal )?residents of bosnia|\bopen to (?:bih|bosnian|local) (?:citizens|nationals)\b|\bdržavljan\w* (?:BiH|Bosne)|\bdržavljanstvo BiH\b", re.I)
CITIZENSHIP_EU = re.compile(r"\bcitizen of a member state of the european union\b|\bEU citizens? only\b|\bnationals? of (?:an? )?(?:EU )?member states?\b|\bdržavljan\w* (?:neke )?(?:države članice )?EU\b", re.I)
REMOTE = re.compile(r"\bremote[- ](?:first|based|work\w*|position|with travel)\b|\bremotely\b|\bfully remote\b|\bhome[- ]based\b|\bwork(?:ing)? from home\b|\brad od kuće\b|\brad na daljinu\b|\bRemote \|", re.I)
HYBRID = re.compile(r"\bhybrid\b|\bhibridn\w*", re.I)
FULL_TIME = re.compile(r"\bfull[- ]time\b|\bpuno radno vrijeme\b|\bpunim radnim vremenom\b", re.I)
PART_TIME = re.compile(r"\bpart[- ]time\b|\bnepuno radno vrijeme\b|\bnepunim radnim vremenom\b", re.I)
CURRENCY = r"(?:EUR(?:O|OS)?|€|BAM|KM|USD|US\$|\$|CHF)"
AMOUNT = r"\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
PERIOD = r"(?:\s*(?:per|a|/)\s*(?:month|year|annum|hour|day)|\s*(?:mjesečno|godišnje|neto|bruto|gross|net)(?:\s+(?:mjesečno|godišnje|per month|per year|monthly))?|\s+monthly|\s+annually)?"
SALARY = re.compile(r"(?:up to\s+|do\s+|from\s+|od\s+)?(?:" + CURRENCY + r"\s?(?:" + AMOUNT + r")(?:\s?(?:-|–|to|do)\s?(?:" + CURRENCY + r"\s?)?(?:" + AMOUNT + r"))?|(?:" + AMOUNT + r")(?:\s?(?:-|–|to|do)\s?(?:" + AMOUNT + r"))?\s?" + CURRENCY + r")" + PERIOD, re.I)
SALARY_CUE = re.compile(r"\bsalary\b|\bcompensation\b|\bremuneration\b|\bpay\b|\bfee\b|\bplat\w*|\bnaknad\w*|\bprimanj\w*|\bzarad\w*", re.I)
SALARY_NOT_STATED = re.compile(r"\b(?:salary|compensation)\s*:?\s*(?:not specified|competitive|tbd|negotiable)\b", re.I)
MONTHS = r"(?:jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*|januar\w*|februar\w*|mart\w*|april\w*|maj\w*|juni?\w*|juli?\w*|august\w*|septemb\w*|oktob\w*|novemb\w*|decemb\w*)"
DURATION = re.compile(r"\b(?:duration|contract (?:length|period|duration)|trajanj\w*(?: od)?|period angažmana|(?:na |za )?period od|assignment duration|for a period of)\s*(?:of the (?:contract|assignment)\s*)?:?\s*((?:up to |do |approximately |approx\. )?" + NUMBER + r"\s*(?:\(\d+\)\s*)?(?:months?|years?|weeks?|working days|mjesec\w*|godin\w*|sedmic\w*|radnih dana)|" + MONTHS + r"\s+\d{4}\s*[-–]\s*" + MONTHS + r"\s+\d{4})", re.I)
TITLE_DURATION = re.compile(r"\b" + NUMBER + r"\s*(?:months?|mjesec\w*)\b", re.I)
GRADE = re.compile(r"\b(?:grade|level|series/grade|razred)\s*:?\s*([A-Z]{1,4}\s?-?\s?\d{1,2}|NO[A-D]|IS)\b|\b(NO[A-D]|G-?[1-7]|P-?[1-6]|D-?[12]|LCH-?\d{1,2}|NPSA-?\d{1,2}|SB-?[1-5]|LICA-?\d{1,2}|LE-?\d{1,2}|FSN-?\d{1,2})\b|\((S[1-4])\)")

SENTENCE_END = re.compile(r"(?<!\be\.g)(?<!\bi\.e)(?<!\betc)(?<!\bapprox)(?<!\bNo)[.!?;](?=\s+[\"“„(]?[A-ZČĆŠĐŽ0-9])|\s[▪•●◦]\s|\s(?=\d{1,2}\.\s+[A-ZČĆŠĐŽ])")
STOP_AFTER_EDUCATION = re.compile(r"\b(?:experience|iskustv\w*|languages?:|jezi\w*|competenc\w*|skills|vještin\w*|knowledge|poznavanj\w*)\b", re.I)


def sentences(text):
    """(start, end) spans of sentence-like pieces of flattened text."""
    spans, start = [], 0
    for match in SENTENCE_END.finditer(text):
        spans.append((start, match.end()))
        start = match.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def quote(text, start, end, limit=260):
    """A short quote around a match, trimmed to whole words."""
    piece = re.sub(r"\s+", " ", text[start:end]).strip()
    if len(piece) > limit:
        piece = piece[:limit].rsplit(" ", 1)[0] + " …"
    return piece


def number(token):
    token = token.lower()
    return int(token) if token.isdecimal() else WORD_NUMBERS.get(token)


# Section headings: a degree listed under "Desirable qualifications" is an asset, not the minimum.
DESIRABLE_HEADING = re.compile(r"\b(?:desirable|desired|preferred|additional) (?:qualifications|requirements|skills)\b|\bdesirables?\s*:|\bassets?\s*:|\bpoželjn\w* (?:kvalifikacij\w*|uslov\w*|uvjet\w*)|\bpoželjno\s*:|\bprednost\w*\s*:", re.I)
REQUIRED_HEADING = re.compile(r"\b(?:essential|required|minimum|mandatory) (?:qualifications|requirements|skills)\b|\b(?:mandatory|requirements|qualifications)\s*:|\b(?:attributes|competencies|remarks|employment conditions|duties|responsibilities)\b|\bobavezn\w* (?:kvalifikacij\w*|uslov\w*|uvjet\w*)", re.I)


def in_desirable_section(text, position):
    """Whether the nearest section heading before this position introduces desirable qualifications."""
    desirable = [match.end() for match in DESIRABLE_HEADING.finditer(text, 0, position)]
    if not desirable:
        return False
    return not REQUIRED_HEADING.search(text, desirable[-1], position)


def education(text, spans):
    found, quotes, field_hits = set(), [], {}
    for start, end in spans:
        piece = text[start:end]
        if not EDUCATION_CUE.search(piece) or in_desirable_section(text, start):
            continue
        levels = {level for level, pattern in LEVEL_PATTERNS.items() if pattern.search(piece)}
        if not levels:
            continue
        found |= levels
        quotes.append(quote(text, start, end))
        # The field of study follows the degree ("degree in Law, Economics …") or, in local adverts, precedes it ("pravni fakultet").
        for match in re.finditer(r"degree|education|diploma|qualification|fakultet\w*|studij\w*|sprem\w*|bachelor\w*|master\w*", piece, re.I):
            before = " ".join(piece[:match.start()].split()[-3:])
            after = piece[match.end():match.end() + 240]
            if stop := STOP_AFTER_EDUCATION.search(after):
                after = after[:stop.start()]
            window = f"{before} {match.group()} {after}"
            for slug, label, pattern in FIELDS:
                if re.search(pattern, window, re.I):
                    field_hits.setdefault(slug, quote(text, start, end))
    if not found:
        return {}, {}
    level = min(found, key=LEVEL_RANK.get)
    return {"level": level, "levels": sorted(found, key=LEVEL_RANK.get), "quote": " … ".join(quotes[:2])}, field_hits


def experience(text, spans):
    if match := NO_EXPERIENCE.search(text):
        return {"years": 0, "quote": quote(text, *span_around(spans, match.start()))}
    best = None
    for start, end in spans:
        piece = text[start:end]
        if not EXPERIENCE_CUE.search(piece):
            continue
        for match in YEARS.finditer(piece):
            years = number(match.group(1))
            if years is None or not 1 <= years <= 30:
                continue
            before, after = piece[:match.start()], piece[match.end():]
            # Inside brackets is an alternative or a course length ("(8 years with a first-level degree)", "education (4 years)").
            if before.rstrip().endswith("(") or YEARS_NOT_REQUIREMENT.search(before[-60:]) or YEARS_SUB_REQUIREMENT.search(after[:60]):
                continue
            # The number must count experience: "N years of … experience", "N years' experience", or "Experience: minimum N years".
            near = after[:140]
            if stop := re.search(r"[.;]\s|\bor\b(?!\s+(?:equivalent|related))", near):
                near_after = near[:stop.start()]
            else:
                near_after = near
            if not (EXPERIENCE_CUE.search(near_after) or EXPERIENCE_CUE.search(before[-90:])):
                continue
            if best is None or years < best[0]:
                best = (years, quote(text, start, end))
    return {"years": best[0], "quote": best[1]} if best else {}


def span_around(spans, position):
    return next(((a, b) for a, b in spans if a <= position < b), (max(0, position - 120), position + 120))


def languages(text, spans):
    required, desirable, quotes = [], [], []
    for start, end in spans:
        piece = text[start:end]
        if not LANGUAGE_CUE.search(piece):
            continue
        hits = []
        for code, label, pattern in LANGUAGES:
            if match := re.search(pattern, piece, re.I):
                hits.append((code, match))
        if not hits:
            continue
        # "Documents … in English language" is about the application, not a requirement.
        if re.search(r"\b(?:application|cv|curriculum|cover letter|motivation letter|documents?|form|translations?|prijav\w*|dokument\w*)\b[^.]{0,60}\b(?:in|na)\s+(?:the\s+)?(?:english|engleskom)", piece, re.I) and not re.search(r"\bfluen|\bproficien|\bcommand of|\bknowledge of|\bpoznavanj|\bspeaker", piece, re.I):
            continue
        quotes.append(quote(text, start, end))
        for code, match in hits:
            target = desirable if qualified_as_asset(piece, match) else required
            if code not in required and code not in target:
                target.append(code)
    desirable = [code for code in desirable if code not in required]
    if not required and not desirable:
        return {}
    return {"required": required, "desirable": desirable, "quote": " … ".join(quotes[:2])}


def qualified_as_asset(piece, match):
    """Whether "an asset", "desirable" or similar qualifies this mention: only in the words right after it, and only before a "required"."""
    after = re.split(r"[;.]\s|\s[▪•●]\s", piece[match.start():match.end() + 100], maxsplit=1)[0]
    asset, required = ASSET.search(after), re.search(r"\b(?:required|mandatory|must|essential|obavez\w*|neophod\w*|potreb\w*)\b", after, re.I)
    return bool(asset and not (required and required.start() < asset.start()))


def flag(pattern, text, spans):
    match = pattern.search(text)
    if not match:
        return {}
    start, end = span_around(spans, match.start())
    return {"required": not qualified_as_asset(text[start:end], re.search(pattern, text[start:end]) or match), "quote": quote(text, start, end)}


def salary(text, spans):
    for start, end in spans:
        piece = text[start:end]
        if not SALARY_CUE.search(piece) or SALARY_NOT_STATED.search(piece):
            continue
        for match in SALARY.finditer(piece):
            value = re.sub(r"\s+", " ", match.group()).strip()
            amount = re.search(AMOUNT, value).group()
            # Thousands separators go ("2.400", "1,890.00", "30 000"); what is left before a decimal mark is the whole amount.
            whole = re.split(r"[.,]", re.sub(r"[.,\s](?=\d{3}(?:\D|$))", "", amount))[0]
            # Years ("2026 EUR") and tiny figures are not salaries.
            if len(whole) < 3 or re.fullmatch(r"20\d\d", whole):
                continue
            return {"text": value, "quote": quote(text, start, end)}
    return {}


def extract(title, text):
    """The requirements stated in a vacancy, each with its source quote. Unclear facts are omitted."""
    text = text or ""
    spans = sentences(text)
    from .translation import detect_language
    result = {"version": VERSION}
    if language := detect_language(f"{title} {text}"):
        result["language"] = language
    edu, field_hits = education(text, spans)
    if edu:
        result["education"] = edu
    if field_hits:
        result["fields"] = list(field_hits)
        result["fields_quote"] = next(iter(field_hits.values()))
    if exp := experience(text, spans):
        result["experience"] = exp
    if langs := languages(text, spans):
        result["languages"] = langs
    if driving := flag(DRIVING, text, spans):
        result["driving_license"] = driving
    if match := CITIZENSHIP_BIH.search(text):
        result["citizenship"] = {"value": "bih", "quote": quote(text, *span_around(spans, match.start()))}
    elif match := CITIZENSHIP_EU.search(text):
        result["citizenship"] = {"value": "eu", "quote": quote(text, *span_around(spans, match.start()))}
    if match := REMOTE.search(text):
        result["remote"] = {"value": "remote", "quote": quote(text, *span_around(spans, match.start()))}
    elif match := HYBRID.search(text):
        result["remote"] = {"value": "hybrid", "quote": quote(text, *span_around(spans, match.start()))}
    full, part = FULL_TIME.search(text), PART_TIME.search(text)
    if bool(full) != bool(part):
        match = full or part
        result["work_time"] = {"value": "full" if full else "part", "quote": quote(text, *span_around(spans, match.start()))}
    if pay := salary(text, spans):
        result["salary"] = pay
    if match := DURATION.search(text):
        result["duration"] = {"text": re.sub(r"\s+", " ", match.group(1).replace("�", "-")).strip(), "quote": quote(text, *span_around(spans, match.start()))}
    elif match := TITLE_DURATION.search(title or ""):
        result["duration"] = {"text": match.group(), "quote": title}
    if match := GRADE.search(f"{title} {text[:3000]}"):
        grade = next(group for group in match.groups() if group)
        result["grade"] = {"text": re.sub(r"\s+", "", grade).upper()}
    return result


PROTECTABLE = ("education_level", "experience_years", "fields_of_study")


def apply(job):
    """Refresh a job's extracted requirements; fields an admin corrected keep their value. Returns the changed field names."""
    found = extract(job.title, job.raw_text)
    values = {
        "requirements": found,
        "education_level": found.get("education", {}).get("level", ""),
        "experience_years": found.get("experience", {}).get("years"),
        "fields_of_study": found.get("fields", []),
    }
    protected = set(job.manually_edited_fields) | set((job.field_evidence or {}).get("ai_fields", []))
    changed = []
    for field, value in values.items():
        if field in protected or getattr(job, field) == value:
            continue
        setattr(job, field, value)
        changed.append(field)
    return changed


def tags(job):
    """Short labels for a job card, most useful first, in the interface language."""
    found = job.requirements or {}
    labels = []
    if job.education_level:
        labels.append(str(dict(EDUCATION_LEVELS)[job.education_level]))
    if job.experience_years is not None:
        labels.append(gettext("Bez iskustva") if job.experience_years == 0 else gettext("%(years)s+ god. iskustva") % {"years": job.experience_years})
    labels += [str(FIELD_LABELS[slug]) for slug in job.fields_of_study[:2] if slug in FIELD_LABELS]
    if found.get("driving_license", {}).get("required"):
        labels.append(gettext("Vozačka dozvola"))
    if remote := found.get("remote", {}).get("value"):
        labels.append(gettext("Rad na daljinu") if remote == "remote" else gettext("Hibridni rad"))
    return labels


def details(job):
    """Rows for the job page: (label, value, quote)."""
    found = job.requirements or {}
    rows = []
    if job.education_level:
        levels = found.get("education", {}).get("levels", [])
        value = str(dict(EDUCATION_LEVELS)[job.education_level])
        higher = [str(dict(EDUCATION_LEVELS)[level]) for level in levels if LEVEL_RANK[level] > LEVEL_RANK[job.education_level]]
        if higher:
            value += " " + gettext("(oglas spominje i: %(levels)s)") % {"levels": ", ".join(higher).lower()}
        rows.append((gettext("Minimalno obrazovanje"), value, found.get("education", {}).get("quote", "")))
    if job.fields_of_study:
        rows.append((gettext("Oblast studija"), ", ".join(str(FIELD_LABELS.get(slug, slug)) for slug in job.fields_of_study), found.get("fields_quote", "")))
    if job.experience_years is not None:
        years = job.experience_years
        value = gettext("Nije potrebno") if years == 0 else gettext("Najmanje %(count)s %(years)s") % {"count": years, "years": plural(years, ("godina", "godine", "godina"), ("year", "years"))}
        rows.append((gettext("Radno iskustvo"), value, found.get("experience", {}).get("quote", "")))
    if langs := found.get("languages"):
        parts = [str(LANGUAGE_LABELS[code]) for code in langs.get("required", [])]
        parts += [gettext("%(language)s (prednost)") % {"language": LANGUAGE_LABELS[code]} for code in langs.get("desirable", [])]
        rows.append((gettext("Jezici"), ", ".join(parts), langs.get("quote", "")))
    if driving := found.get("driving_license"):
        rows.append((gettext("Vozačka dozvola"), gettext("Obavezna") if driving["required"] else gettext("Prednost"), driving["quote"]))
    if citizenship := found.get("citizenship"):
        rows.append((gettext("Državljanstvo"), gettext("Samo državljani BiH (ili osobe s prebivalištem)") if citizenship["value"] == "bih" else gettext("Samo državljani EU"), citizenship["quote"]))
    return rows


def terms(job):
    """Contract terms for the job page: (label, value, quote)."""
    found = job.requirements or {}
    rows = []
    if grade := found.get("grade"):
        rows.append((gettext("Razred / nivo"), grade["text"], ""))
    if duration := found.get("duration"):
        rows.append((gettext("Trajanje"), duration["text"], duration["quote"]))
    if pay := found.get("salary"):
        rows.append((gettext("Plata / naknada"), pay["text"], pay["quote"]))
    if work := found.get("work_time"):
        rows.append((gettext("Radno vrijeme"), gettext("Puno radno vrijeme") if work["value"] == "full" else gettext("Nepuno radno vrijeme"), work["quote"]))
    if remote := found.get("remote"):
        rows.append((gettext("Način rada"), gettext("Rad na daljinu") if remote["value"] == "remote" else gettext("Hibridni rad"), remote["quote"]))
    return rows
