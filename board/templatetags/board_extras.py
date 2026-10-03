from django import template
from django.utils.translation import gettext

from board.text import plural

register = template.Library()


@register.filter
def bs_plural(count, forms):
    """{{ n }} {{ n|bs_plural:"rezultat,rezultata,rezultata|result,results" }}: Bosnian forms, then English after a bar."""
    bs_forms, _, en_forms = forms.partition("|")
    bs_forms = bs_forms.split(",")
    return plural(count, bs_forms, en_forms.split(",") if en_forms else bs_forms[:1] + bs_forms[2:])


@register.inclusion_tag("board/_deadline.html")
def deadline(job, variant="card"):
    """The deadline in one shape for the job card, the job page summary and the sticky apply bar: label, date and a countdown coloured by urgency."""
    days = getattr(job, "days_left", None)
    if days is None or days < 0:
        countdown, urgency = "", ""
    elif days == 0:
        countdown, urgency = gettext("Ističe danas"), "today"
    elif days == 1:
        countdown, urgency = gettext("Ističe sutra"), "today"
    else:
        countdown = plural(days, ["Još %(days)s dan", "Još %(days)s dana", "Još %(days)s dana"], ["%(days)s day left", "%(days)s days left"]) % {"days": days}
        urgency = "soon" if days <= 7 else "open"
    return {"job": job, "variant": variant, "countdown": countdown, "urgency": urgency}
