import logging
from datetime import timedelta
from django.db import connection

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Min, Max
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

        self._iteration_destroy(days=days, date_field_name="created_at", model=RequestLogRecord, hours_range=3)
        self._iteration_destroy(days=days, date_field_name="created_at", model=RequestLogChange, hours_range=3)

    def _iteration_destroy(self, model, date_field_name: str, hours_range=3, days=3, id_batch_size=1000):
        current_start = model.objects.aggregate(
            min_date=Min(f'{date_field_name}')
        )['min_date']

        if not current_start:
            return

        current_end = current_start + timedelta(hours=hours_range)
        if current_start > current_end:
            return

        while current_end <= timezone.now() - timedelta(days=days):
            id_range = model.objects.filter(
                **{
                    f"{date_field_name}__gte": current_start,
                    f"{date_field_name}__lt": current_end,
                }
            ).aggregate(
                min_id=Min('id'),
                max_id=Max('id')
            )

            min_id = id_range['min_id']
            max_id = id_range['max_id']

            if min_id and max_id:
                total_deleted = 0
                current_id = min_id

                while current_id <= max_id:
                    batch_end = min(current_id + id_batch_size - 1, max_id)

                    deleted_count = model.objects.filter(
                        id__gte=current_id,
                        id__lte=batch_end,
                        **{
                            f"{date_field_name}__gte": current_start,
                            f"{date_field_name}__lt": current_end,
                        }
                    ).delete()[0]

                    total_deleted += deleted_count
                    current_id = batch_end + 1

                logger.info(f"Deleted {total_deleted} records from {current_start} to {current_end}")
            else:
                logger.info(f"No records from {current_start} to {current_end}")

            current_start = current_end
            current_end = current_start + timedelta(hours=hours_range)

        if timezone.now().weekday() == 6:
            self._reindex_table_concurrently(table_name=f"public.{model._meta.db_table}")

    # Be careful
    def _reindex_table_concurrently(self, table_name: str, ):
        logger.info(f"Start reindex {table_name} table concurrently")
        with connection.cursor() as cursor:
            cursor.execute(f"REINDEX TABLE CONCURRENTLY {table_name};")
        logger.info(f"{table_name} table is reindexed")
