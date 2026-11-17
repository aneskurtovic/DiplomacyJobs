from django.db import migrations


OLD_URL = "https://www.mfa.gr/missionsabroad/en/bosnia-herzegovina-en/news/"
NEW_URL = "https://www.mfa.gr/bosnia-herzegovina/en/category/news/embassy-news/"
OLD_CONFIG = {
    "path_contains": "/bosnia-herzegovina-en/news/",
    "content_selector": "#sitecontent .inside",
    "published_selector": ".item_createdate",
    "page_item_selector": "li.sectiontableentry1, li.sectiontableentry2",
}
NEW_CONFIG = {
    "path_contains": "/bosnia-herzegovina/en/",
    "link_selector": ".module-post-news a[href]",
    "listing_selector": "main .module-post-news",
    "content_selector": "main article",
    "published_selector": "article p.text-sm",
    "page_item_selector": ".module-post-news .swiper-slide",
    "next_page_selector": "a.next.page-numbers",
}


def move(apps, old_url, new_url, remove, settings):
    Source = apps.get_model("board", "Source")
    for source in Source.objects.filter(url=old_url, adapter="generic"):
        if Source.objects.filter(organization_id=source.organization_id, url=new_url).exists():
            raise RuntimeError("Duplicate Greek news source; resolve before migrating")
        config = dict(source.adapter_config or {})
        for key in remove:
            config.pop(key, None)
        config.update(settings)
        config.update(allow_empty=True, stop_at_older_page=True)
        source.url, source.adapter_config = new_url, config
        source.save(update_fields=["url", "adapter_config"])


def forward(apps, schema_editor):
    move(apps, OLD_URL, NEW_URL, OLD_CONFIG, NEW_CONFIG)


def backward(apps, schema_editor):
    move(apps, NEW_URL, OLD_URL, NEW_CONFIG, OLD_CONFIG)


class Migration(migrations.Migration):
    dependencies = [("board", "0044_sweden_beta_api_source")]
    operations = [migrations.RunPython(forward, backward)]
