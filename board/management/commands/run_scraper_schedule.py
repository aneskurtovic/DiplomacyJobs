import time
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run daily scraping in the dedicated scheduler container"

    def handle(self, *args, **options):
        while True:
            try:
                call_command("scrape_jobs")
            except Exception as exc:
                self.stderr.write(str(exc))
            time.sleep(24 * 60 * 60)
