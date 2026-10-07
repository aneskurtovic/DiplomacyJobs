from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("board", "0036_job_closed_reason_archive")]

    operations = [
        migrations.AlterField(
            model_name="job",
            name="closed_reason",
            field=models.CharField(blank=True, choices=[("deadline", "Istekao rok"), ("missing", "Nestao sa izvora"), ("stale", "Bez roka, zastario"), ("withdrawn", "Povučen na izvoru"), ("manual", "Zatvoren ručno"), ("archive", "Preuzet iz arhive izvora"), ("duplicate", "Duplikat službenog oglasa")], max_length=20),
        ),
    ]
