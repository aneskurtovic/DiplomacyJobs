from django.db import migrations


OLD_URL = "https://www.swedenabroad.se/en/embassies/bosnia-and-herzegovina-sarajevo/current/news2/"
NEW_URL = "https://beta-api.swedenabroad.se/en/embassies/bosnia-and-herzegovina-sarajevo/current/news2/"


def move_sweden_source(apps, schema_editor):
    Source = apps.get_model("board", "Source")
    source = Source.objects.filter(
        organization__name="Kingdom of Sweden",
        url=OLD_URL,
    ).first()
    if source is None:
        return

    if Source.objects.filter(organization_id=source.organization_id, url=NEW_URL).exists():
        raise RuntimeError(
            "Cannot move the Sweden source to beta-api: a source for that URL already exists. "
            "Resolve the duplicate before applying this migration."
        )

    source.url = NEW_URL
    source.save(update_fields=["url"])


def restore_sweden_source(apps, schema_editor):
    Source = apps.get_model("board", "Source")
    source = Source.objects.filter(
        organization__name="Kingdom of Sweden",
        url=NEW_URL,
    ).first()
    if source is None:
        return

    if Source.objects.filter(organization_id=source.organization_id, url=OLD_URL).exists():
        raise RuntimeError(
            "Cannot restore the Sweden source URL: a source for the previous URL already exists."
        )

    source.url = OLD_URL
    source.save(update_fields=["url"])


class Migration(migrations.Migration):
    dependencies = [("board", "0043_candidateprofile_candidatedigest_candidatefeedback_and_more")]

    operations = [migrations.RunPython(move_sweden_source, restore_sweden_source)]
