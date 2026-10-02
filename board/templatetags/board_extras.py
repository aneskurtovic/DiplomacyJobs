from django import template

from board.text import bs_plural as choose

register = template.Library()


@register.filter
def bs_plural(count, forms):
    """{{ n }} {{ n|bs_plural:"rezultat,rezultata,rezultata" }}"""
    one, few, many = forms.split(",")
    return choose(count, one, few, many)
