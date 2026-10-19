"""Candidate discovery, private profiles, and gated account flows."""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .candidate_forms import CandidateProfileForm, CandidateSignupForm, PreferencesForm
from .candidate_mail import account_mail_ready, alert_unsubscribe_user, send_activation, signup_open
from .matching import rank_jobs
from .models import CandidateFeedback, CandidateProfile, DiscoveryMetric, Job
from .views import visible_jobs


logger = logging.getLogger(__name__)


def count_metric(kind, job=None):
    metric, _ = DiscoveryMetric.objects.get_or_create(day=timezone.localdate(), kind=kind, job=job)
    DiscoveryMetric.objects.filter(pk=metric.pk).update(count=F("count") + 1)


def private(response):
    response["Cache-Control"] = "private, no-store"
    response["Vary"] = "Cookie"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def for_you(request):
    if request.method == "POST":
        form = PreferencesForm(request.POST)
        if form.is_valid():
            request.session["candidate_preview"] = form.preferences()
            request.session["candidate_preview_started"] = True
            request.session["candidate_hidden_jobs"] = []
            return redirect("for_you")
    else:
        profile = getattr(request.user, "candidate_profile", None) if request.user.is_authenticated else None
        initial = request.session.get("candidate_preview", profile.preferences if profile else {})
        form = PreferencesForm(initial=initial)

    matches = []
    if request.session.get("candidate_preview_started") or request.user.is_authenticated:
        if request.method == "POST":
            preferences = request.session.get("candidate_preview", {})
        else:
            preferences = form.initial
        hidden = set(request.session.get("candidate_hidden_jobs", []))
        if request.user.is_authenticated:
            hidden.update(CandidateFeedback.objects.filter(user=request.user).values_list("job_id", flat=True))
        jobs = list(visible_jobs().select_related("source__organization"))
        matches = rank_jobs(jobs, preferences, hidden)
        today = timezone.localdate().isoformat()
        last = request.session.get("candidate_last_visit")
        if last != today:
            count_metric("for_you_visit")
            if last:
                count_metric("for_you_return")
            request.session["candidate_last_visit"] = today
            if not matches:
                count_metric("no_match")
    response = render(request, "board/for_you.html", {"form": form, "matches": matches,
                                                        "preview_started": request.session.get("candidate_preview_started") or request.user.is_authenticated})
    return private(response)


@require_POST
def not_relevant(request, pk):
    job = get_object_or_404(visible_jobs(), pk=pk)
    if request.user.is_authenticated:
        _, created = CandidateFeedback.objects.get_or_create(user=request.user, job=job)
    else:
        hidden = set(request.session.get("candidate_hidden_jobs", []))
        created = job.pk not in hidden
        hidden.add(job.pk)
        request.session["candidate_hidden_jobs"] = list(hidden)[-100:]
    if created:
        count_metric("not_relevant", job)
    return redirect("for_you")


def official_application(request, pk):
    job = get_object_or_404(Job, pk=pk)
    if request.GET.get("from") == "for_you":
        count_metric("matched_clickout", job)
    return redirect(job.application_url or job.canonical_url)


def candidate_signup(request):
    if not signup_open():
        raise Http404
    form = CandidateSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = get_user_model()(username=email, email=email, is_active=False)
        user.set_password(form.cleaned_data["password1"])
        try:
            user.save()
        except IntegrityError:
            form.add_error("email", _("Račun s ovom e-mail adresom već postoji."))
        else:
            CandidateProfile.objects.create(user=user, language=request.LANGUAGE_CODE,
                                            preferences=request.session.get("candidate_preview", {}))
            try:
                send_activation(request, user, request.LANGUAGE_CODE)
            except Exception:
                logger.exception("Candidate activation email failed")
                user.delete()
                form.add_error(None, _("Potvrdu trenutno nije moguće poslati. Pokušajte ponovo kasnije."))
            else:
                return private(render(request, "board/candidate_signup_done.html"))
    return private(render(request, "board/candidate_signup.html", {"form": form}))


def candidate_activate(request, uidb64, token):
    try:
        user = get_user_model().objects.get(pk=urlsafe_base64_decode(uidb64).decode())
    except (ValueError, TypeError, OverflowError, get_user_model().DoesNotExist):
        user = None
    if user and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        login(request, user)
        messages.success(request, _("Račun je potvrđen."))
        return redirect("candidate_profile")
    return private(render(request, "board/candidate_activation_invalid.html", status=400))


@login_required
def candidate_profile(request):
    profile, _created = CandidateProfile.objects.get_or_create(user=request.user)
    initial = dict(profile.preferences)
    initial.update(job_alert=bool(profile.job_alert_opt_in_at), product_email=bool(profile.product_email_opt_in_at))
    form = CandidateProfileForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        profile.preferences = form.preferences()
        profile.language = request.LANGUAGE_CODE
        now = timezone.now()
        profile.job_alert_opt_in_at = (profile.job_alert_opt_in_at or now) if form.cleaned_data["job_alert"] else None
        profile.product_email_opt_in_at = (profile.product_email_opt_in_at or now) if form.cleaned_data["product_email"] else None
        profile.save()
        request.session["candidate_preview"] = profile.preferences
        request.session["candidate_preview_started"] = True
        messages.success(request, _("Postavke su sačuvane."))
        return redirect("candidate_profile")
    return private(render(request, "board/candidate_profile.html", {"form": form}))


@login_required
@require_POST
def candidate_delete(request):
    if not request.user.check_password(request.POST.get("password", "")):
        messages.error(request, _("Pogrešna lozinka. Račun nije obrisan."))
        return redirect("candidate_profile")
    user = request.user
    logout(request)
    user.delete()
    request.session.pop("candidate_preview", None)
    request.session.pop("candidate_preview_started", None)
    messages.success(request, _("Račun je obrisan."))
    return redirect("jobs")


def candidate_password_reset(request):
    if not account_mail_ready():
        raise Http404
    view = auth_views.PasswordResetView.as_view(
        template_name="board/candidate_password_reset.html",
        email_template_name="board/emails/password_reset.txt",
        subject_template_name="board/emails/password_reset_subject.txt",
        success_url=reverse("candidate_password_reset_done"),
    )
    return private(view(request))


def candidate_privacy(request):
    return render(request, "board/candidate_privacy.html", {"operator": settings.CANDIDATE_OPERATOR_NAME,
                                                            "privacy_email": settings.CANDIDATE_PRIVACY_EMAIL,
                                                            "email_processor": settings.CANDIDATE_EMAIL_PROCESSOR})


def candidate_unsubscribe(request, token):
    user = alert_unsubscribe_user(token)
    if not user:
        return private(render(request, "board/candidate_activation_invalid.html", status=400))
    if request.method == "POST":
        profile = getattr(user, "candidate_profile", None)
        if profile:
            profile.job_alert_opt_in_at = None
            profile.save(update_fields=["job_alert_opt_in_at", "updated_at"])
        return private(render(request, "board/candidate_unsubscribe_done.html"))
    return private(render(request, "board/candidate_unsubscribe.html"))
