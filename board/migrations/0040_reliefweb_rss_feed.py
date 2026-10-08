from django.db import migrations

HTML = "https://reliefweb.int/jobs?advanced-search=%28C40%29"
FEED = "https://reliefweb.int/jobs/rss.xml?advanced-search=%28C40%29"


def move(old, new):
    # The registry matches sources by URL; moving the existing row keeps its jobs and run history, and a later import finds it.
    def run(apps, schema_editor):
        Source = apps.get_model("board", "Source")
        if not Source.objects.filter(url=new).exists():
            Source.objects.filter(url=old).update(url=new)
    return run


class Migration(migrations.Migration):
    dependencies = [("board", "0039_organization_name_en")]

    operations = [migrations.RunPython(move(HTML, FEED), move(FEED, HTML))]
