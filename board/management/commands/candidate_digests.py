"""Preview weekly matches, or send one digest per opted-in candidate and week."""

from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from board.candidate_mail import account_mail_ready, send_job_digest
from board.matching import rank_jobs
from board.models import CandidateDigest, CandidateFeedback, CandidateProfile, JobAlertDelivery
from board.views import visible_jobs


class Command(BaseCommand):
    help = "Preview candidate digests by default. --send requires all mail and alert switches."

    def add_arguments(self, parser):
        parser.add_argument("--send", action="store_true", help="Actually send opted-in weekly digests")

    def handle(self, *args, **options):
        sending = options["send"]
        active_since = None
        if sending:
            if not (settings.JOB_ALERTS_ENABLED and account_mail_ready() and settings.PUBLIC_BASE_URL):
                raise CommandError("Job alerts, account mail, and PUBLIC_BASE_URL must all be configured before --send")
            try:
                active_date = datetime.strptime(settings.JOB_ALERTS_ACTIVE_SINCE, "%Y-%m-%d").date()
            except ValueError as error:
                raise CommandError("Set JOB_ALERTS_ACTIVE_SINCE to an ISO date before --send") from error
            active_since = timezone.make_aware(datetime.combine(active_date, time.min))

        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        now = timezone.now()
        current_jobs = list(visible_jobs().select_related("source__organization"))
        candidate_count = digest_count = job_count = 0

        profiles = CandidateProfile.objects.filter(user__is_active=True, job_alert_opt_in_at__isnull=False).select_related("user")
        for profile in profiles.iterator():
            candidate_count += 1
            if CandidateDigest.objects.filter(user=profile.user, week_start=week_start).exists():
                continue
            if sending:
                cutoff = max(active_since, profile.job_alert_opt_in_at)
                delivered = set(JobAlertDelivery.objects.filter(user=profile.user).values_list("job_id", flat=True))
                jobs = [job for job in current_jobs if job.published_at and job.published_at >= cutoff and job.pk not in delivered]
            else:
                jobs = current_jobs
            hidden = CandidateFeedback.objects.filter(user=profile.user).values_list("job_id", flat=True)
            matches = rank_jobs(jobs, profile.preferences, hidden)
            # A digest needs an actual matching signal, and never emails cautioned jobs.
            selected = [match for match in matches if match.score >= 3 and not match.cautions][:5]
            if not selected:
                continue
            digest_count += 1
            job_count += len(selected)
            if not sending:
                continue

            # Reserve the week before sending. A failed or uncertain attempt needs manual
            # review; automatic replay could deliver duplicate mail.
            with transaction.atomic():
                digest, created = CandidateDigest.objects.get_or_create(
                    user=profile.user, week_start=week_start,
                    defaults={"job_ids": [match.job.pk for match in selected], "status": "pending"},
                )
            if not created:
                continue
            try:
                send_job_digest(profile, selected)
            except Exception:
                digest.status = "needs_review"
                digest.save(update_fields=["status"])
                self.stderr.write(f"Digest for candidate {profile.user_id} needs manual review")
                continue
            with transaction.atomic():
                JobAlertDelivery.objects.bulk_create([
                    JobAlertDelivery(user=profile.user, job=match.job, sent_at=now) for match in selected
                ], ignore_conflicts=True)
                digest.status = "sent"
                digest.sent_at = now
                digest.save(update_fields=["status", "sent_at"])
        mode = "SENT" if sending else "DRY RUN, NO EMAIL OR DATABASE WRITES"
        self.stdout.write(f"{mode}: {candidate_count} opted-in candidates; {digest_count} digests; {job_count} jobs")
