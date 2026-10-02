from django.core.management.base import BaseCommand

from board.ingest import FETCH_ERRORS, TARGET_YEAR, discover_links, fetch, listing_link_in_scope, open_client
from board.models import Source


class Command(BaseCommand):
    help = "Fetch each source's listing and report what its adapter finds, without writing to the database (for checking access from a new network)"

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Include disabled sources that have an adapter")
        parser.add_argument("--source", type=int)

    def handle(self, *args, **options):
        sources = Source.objects.exclude(adapter="none").select_related("organization").order_by("pk")
        if not options["all"]:
            sources = sources.filter(enabled=True)
        if options["source"]:
            sources = sources.filter(pk=options["source"])
        failures = 0
        for source in sources:
            label = f"{source.pk:>4} {source.adapter:<10} {source.organization.name[:50]}"
            try:
                with open_client(source) as client:
                    _, soup = fetch(client, source.url)
                    if soup is None:
                        raise ValueError("Source listing must be HTML")
                    links = discover_links(client, source, soup, {})
            except FETCH_ERRORS as exc:
                failures += 1
                self.stdout.write(f"FAIL {label}: {str(exc)[:200]}")
                continue
            in_scope = sum(1 for url, title in links if listing_link_in_scope(url, title))
            self.stdout.write(f"OK   {label}: {len(links)} leads, {in_scope} in {TARGET_YEAR} scope")
        self.stdout.write(f"{sources.count() - failures} reachable, {failures} failing")
