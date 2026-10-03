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
