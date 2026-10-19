"""Candidate email boundary. Sending requires an explicit production switch."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import override
from django.utils.translation import gettext as _


def account_mail_ready():
    smtp_ready = (settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and
                  bool(settings.EMAIL_HOST))
    test_mail_ready = (settings.DEBUG and
                       settings.EMAIL_BACKEND == "django.core.mail.backends.locmem.EmailBackend")
    return bool(settings.CANDIDATE_MAIL_ENABLED and settings.DEFAULT_FROM_EMAIL and
                (smtp_ready or test_mail_ready))


def signup_open():
    return bool(settings.CANDIDATE_SIGNUP_ENABLED and account_mail_ready() and
                settings.CANDIDATE_OPERATOR_NAME and settings.CANDIDATE_PRIVACY_EMAIL and
                settings.CANDIDATE_EMAIL_PROCESSOR)


def candidate_navigation(request):
    return {"candidate_signup_open": signup_open(), "candidate_account_mail_ready": account_mail_ready(),
            "job_alerts_active": settings.JOB_ALERTS_ENABLED}


def send_activation(request, user, language):
    if not account_mail_ready():
        raise RuntimeError("Candidate account email delivery is disabled")
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    with override(language):
        url = request.build_absolute_uri(reverse("candidate_activate", args=[uid, token]))
        subject = render_to_string("board/emails/activation_subject.txt").strip()
        body = render_to_string("board/emails/activation.txt", {"url": url})
    if send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False) != 1:
        raise RuntimeError("Candidate activation email was not accepted by the email backend")


def alert_unsubscribe_token(user):
    return signing.dumps(user.pk, salt="candidate-job-alert-unsubscribe")


def alert_unsubscribe_user(token):
    from django.contrib.auth import get_user_model
    try:
        pk = signing.loads(token, salt="candidate-job-alert-unsubscribe")
        return get_user_model().objects.get(pk=pk)
    except (signing.BadSignature, get_user_model().DoesNotExist, TypeError, ValueError):
        return None


def send_job_digest(profile, matches):
    if not (settings.JOB_ALERTS_ENABLED and account_mail_ready()):
        raise RuntimeError("Candidate job alert delivery is disabled")
    user = profile.user
    with override(profile.language):
        subject = _("Novi oglasi za vas · DiplomacyJobs")
        lines = [_('Novi oglasi koji odgovaraju vašim postavkama:'), ""]
        for match in matches:
            lines.append(f"• {match.job.title} — {match.job.employer_label}")
            lines.append(f"  {settings.PUBLIC_BASE_URL}{match.job.get_absolute_url()}")
            if match.unknowns:
                lines.append("  " + _("Neki uslovi nisu navedeni; provjerite službeni oglas."))
            lines.append("")
        lines.append(_("Prijava se podnosi na službenoj stranici poslodavca."))
        lines.append(_("Odjava od obavijesti:"))
        lines.append(f"{settings.PUBLIC_BASE_URL}{reverse('candidate_unsubscribe', args=[alert_unsubscribe_token(user)])}")
    if send_mail(subject, "\n".join(lines), settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False) != 1:
        raise RuntimeError("Candidate digest email was not accepted by the email backend")
