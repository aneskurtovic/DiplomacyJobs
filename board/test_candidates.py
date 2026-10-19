"""Candidate matching, account gates, and dormant email delivery."""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .candidate_mail import alert_unsubscribe_token, signup_open
from .matching import rank_jobs
from .models import CandidateDigest, CandidateProfile, DiscoveryMetric, Job, JobAlertDelivery, Organization, Source
from .views import visible_jobs


STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
          "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
TEST_MAIL = dict(DEBUG=True, CANDIDATE_MAIL_ENABLED=True, CANDIDATE_SIGNUP_ENABLED=True,
                 EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", EMAIL_HOST="",
                 DEFAULT_FROM_EMAIL="jobs@example.com", CANDIDATE_OPERATOR_NAME="DiplomacyJobs",
                 CANDIDATE_PRIVACY_EMAIL="privacy@example.com", CANDIDATE_EMAIL_PROCESSOR="Test Mail")


@override_settings(STORAGES=STATIC)
class CandidateTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Test Organization", kind="international")
        self.source = Source.objects.create(organization=organization, url="https://example.org/jobs",
                                            adapter="generic", status="verified", enabled=True,
                                            last_success_at=timezone.now())

    def job(self, title, number, **kwargs):
        return Job.objects.create(source=self.source, title=title, status="published", city="Sarajevo",
                                  deadline=timezone.localdate() + timedelta(days=10),
                                  canonical_url=f"https://example.org/jobs/{number}", **kwargs)

    def test_unknown_requirements_remain_possible_and_hard_constraints_only_exclude_clear_conflicts(self):
        unknown = self.job("Communications Officer", 1)
        other = self.job("Project Assistant", 2)
        matches = rank_jobs(list(visible_jobs()), {"role": "communications", "education": "bachelor",
                                                  "city": "Mostar", "must_city": False})
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].job, unknown)
        self.assertEqual(matches[0].tier, "possible")
        self.assertTrue(matches[0].unknowns)
        self.assertEqual(rank_jobs([unknown, other], {"city": "Mostar", "must_city": True}), [])
        self.assertEqual(rank_jobs([unknown], {"city": "Sarajevo", "remote": True, "must_remote": True}), [])

    def test_anonymous_preview_feedback_and_clickout_are_private_and_counted(self):
        job = self.job("Communications Officer", 1)
        response = self.client.post(reverse("for_you"), {"role": "communications"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, job.title)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(DiscoveryMetric.objects.get(kind="for_you_visit").count, 1)
        response = self.client.get(reverse("official_application", args=[job.pk]) + "?from=for_you")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], job.canonical_url)
        self.assertEqual(DiscoveryMetric.objects.get(kind="matched_clickout", job=job).count, 1)
        self.client.post(reverse("not_relevant", args=[job.pk]))
        self.assertNotContains(self.client.get(reverse("for_you")), job.title)

    def test_registration_and_all_delivery_are_off_by_default(self):
        self.assertEqual(self.client.get(reverse("candidate_signup")).status_code, 404)
        output = StringIO()
        call_command("candidate_digests", stdout=output)
        self.assertIn("NO EMAIL OR DATABASE WRITES", output.getvalue())
        with self.assertRaises(CommandError):
            call_command("candidate_digests", send=True)

    @override_settings(**{**TEST_MAIL, "DEBUG": False,
                          "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
                          "EMAIL_HOST": "smtp.example.com"})
    def test_console_email_cannot_open_production_signup(self):
        self.assertFalse(signup_open())
        self.assertEqual(self.client.get(reverse("candidate_signup")).status_code, 404)

    @override_settings(**TEST_MAIL)
    def test_signup_activation_profile_and_deletion(self):
        self.job("Communications Officer", 1)
        self.client.post(reverse("for_you"), {"role": "communications"})
        response = self.client.post(reverse("candidate_signup"), {"email": "person@example.com",
                                                                  "password1": "uncommon-long-passphrase",
                                                                  "password2": "uncommon-long-passphrase"})
        self.assertEqual(response.status_code, 200)
        user = get_user_model().objects.get(email="person@example.com")
        self.assertFalse(user.is_active)
        self.assertEqual(user.candidate_profile.preferences["role"], "communications")
        self.assertEqual(len(mail.outbox), 1)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        self.assertEqual(self.client.get(reverse("candidate_activate", args=[uid, token])).status_code, 302)
        self.assertTrue(get_user_model().objects.get(pk=user.pk).is_active)
        self.client.post(reverse("candidate_profile"), {"role": "communications", "job_alert": "on"})
        user.candidate_profile.refresh_from_db()
        self.assertIsNotNone(user.candidate_profile.job_alert_opt_in_at)
        self.client.post(reverse("candidate_delete"), {"password": "uncommon-long-passphrase"})
        self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())

    @override_settings(**TEST_MAIL, JOB_ALERTS_ENABLED=True, PUBLIC_BASE_URL="https://jobs.example.com",
                       JOB_ALERTS_ACTIVE_SINCE=(timezone.localdate() - timedelta(days=1)).isoformat())
    def test_digest_is_dry_by_default_sends_once_and_unsubscribes(self):
        job = self.job("Communications Officer", 1)
        user = get_user_model().objects.create_user(username="person@example.com", email="person@example.com",
                                                     password="uncommon-long-passphrase")
        profile = CandidateProfile.objects.create(user=user, preferences={"role": "communications"},
                                                  job_alert_opt_in_at=timezone.now() - timedelta(days=1))
        output = StringIO()
        call_command("candidate_digests", stdout=output)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(CandidateDigest.objects.count(), 0)
        call_command("candidate_digests", send=True, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(JobAlertDelivery.objects.filter(user=user, job=job).exists())
        call_command("candidate_digests", send=True, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        url = reverse("candidate_unsubscribe", args=[alert_unsubscribe_token(user)])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url)
        profile.refresh_from_db()
        self.assertIsNone(profile.job_alert_opt_in_at)

    @override_settings(**TEST_MAIL)
    def test_password_recovery_and_english_preview(self):
        self.job("Communications Officer", 1)
        get_user_model().objects.create_user(username="person@example.com", email="person@example.com",
                                             password="uncommon-long-passphrase")
        response = self.client.post(reverse("candidate_password_reset"), {"email": "person@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/account/reset/", mail.outbox[0].body)
        response = self.client.post("/en/for-you/", {"role": "communications"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jobs for you")
        self.assertContains(response, "Communications Officer")
