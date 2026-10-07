from django.core.management.base import BaseCommand

from board.dedup import reconcile_aggregator_duplicates


class Command(BaseCommand):
    help = "Close syndicated copies of jobs already held from an official source"

    def handle(self, *args, **options):
        count = reconcile_aggregator_duplicates()
        self.stdout.write(f"{count} syndicated copies closed as duplicates")
