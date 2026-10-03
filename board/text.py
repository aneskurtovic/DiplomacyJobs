import re
import unicodedata


def bs_plural(count, one, few, many):
    """Bosnian count agreement: 1, 21, 31… take the singular; 2–4, 22–24… the 'few' form; the rest the plural."""
    count = abs(int(count))
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def plural(count, bs_forms, en_forms):
    """Count agreement in the active interface language: Bosnian has three forms, English two."""
    from django.utils.translation import get_language
    if (get_language() or "bs").startswith("en"):
        return en_forms[0] if abs(int(count)) == 1 else en_forms[1]
    return bs_plural(count, *bs_forms)


def fold(text):
    """Case- and diacritic-insensitive form for search: "Švicarska", "svicarska" and "ŠVICARSKA" agree. Đ has no decomposition, and dj is its usual ASCII spelling."""
    text = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return "".join(char for char in text if not unicodedata.combining(char)).replace("dj", "d")


MONOGRAM_SKIP = {"u", "i", "za", "of", "the", "in", "and", "to", "for", "bih", "ambasada", "embassy", "konzulat", "consulate", "general", "generalni", "republic", "republike", "republika", "ured", "office"}


def monogram(name, short_name=""):
    """Up to five letters for the employer badge: the registry short name, an acronym in the name ("UNICEF - United Nations…"), or two initials."""
    if short_name:
        return short_name
    acronym = next((word for word in re.findall(r"\b[A-ZČĆŠĐŽ]{2,6}\b", name) if word != "BIH"), "")
    if acronym:
        return acronym
    words = [word for word in re.findall(r"\w+", name) if word.casefold() not in MONOGRAM_SKIP]
    # One remaining word ("Ambasada Italije") gives its first two letters, not a lone initial.
    return (words[0][:2] if len(words) == 1 else "".join(word[0] for word in words[:2])).upper()
