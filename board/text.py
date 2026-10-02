def bs_plural(count, one, few, many):
    """Bosnian count agreement: 1, 21, 31… take the singular; 2–4, 22–24… the 'few' form; the rest the plural."""
    count = abs(int(count))
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many
