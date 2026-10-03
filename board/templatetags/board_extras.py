from django import template

from board.text import plural

register = template.Library()


@register.filter
def bs_plural(count, forms):
    """{{ n }} {{ n|bs_plural:"rezultat,rezultata,rezultata|result,results" }}: Bosnian forms, then English after a bar."""
    bs_forms, _, en_forms = forms.partition("|")
    bs_forms = bs_forms.split(",")
    return plural(count, bs_forms, en_forms.split(",") if en_forms else bs_forms[:1] + bs_forms[2:])
