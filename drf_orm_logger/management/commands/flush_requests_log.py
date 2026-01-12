import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import RequestLogChange, RequestLogRecord

logger = logging.getLogger("default")

class Command(BaseCommand):
    help = "Очистить лог http-запросов от устаревших записей"

    def add_arguments(self, parser):
        parser.add_argument("days", type=int, nargs="?")

    def handle(self, *args, **options):
        days = options.get("days")
        if days is None:
            days = getattr(settings, "REQUESTS_LOGGER", {}).get("FLUSH_DAYS", 14)

        self._iteration_destroy(days=days, model=RequestLogRecord)
        self._iteration_destroy(days=days, model=RequestLogChange)

    def _iteration_destroy(self, days, model):
        days_ago = timezone.now() - timedelta(days=days)
        six_hours = timedelta(hours=6)

        current_start = days_ago - timedelta(days=3)
        current_end = current_start + six_hours

        while current_end <= days_ago:
            deleted_count = model.objects.filter(
                created_at__gte=current_start,
                created_at__lt=current_end
            ).delete()[0]

            logger.info(f"Deleted {deleted_count} records from {current_start} to {current_end}")

            current_start = current_end
            current_end = current_start + six_hours
