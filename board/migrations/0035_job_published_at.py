from django.db import migrations, models


def backfill(apps, schema_editor):
    """Published jobs were public from their first sighting. A closed job left no record of it; one closed by the source (not by a reviewer) with no review reason was published automatically when found."""
    Job = apps.get_model("board", "Job")
    for job in Job.objects.filter(published_at__isnull=True).filter(models.Q(status="published") | models.Q(status="closed", closed_reason__in=("deadline", "missing", "withdrawn", "stale"))):
        if job.status == "published" or not (job.field_evidence or {}).get("review_reason"):
            job.published_at = job.first_seen_at
            job.save(update_fields=["published_at"])


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0034_organization_short_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='published_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
