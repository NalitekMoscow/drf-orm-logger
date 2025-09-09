from typing import Iterator

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q, QuerySet
from django.utils import timezone

from ...models import RequestLogChange, RequestLogRecord
from ...signals import get_models_to_log


class Command(BaseCommand):
    help = "Очистить лог http-запросов от устаревших записей"

    def add_arguments(self, parser):
        parser.add_argument("days", type=int, nargs="?")

    def handle(self, *args, **options):
        days = options.get("days")
        if days is None:
            days = getattr(settings, "REQUESTS_LOGGER", {}).get("FLUSH_DAYS", 14)

        deleted_request_records = (
            self.get_request_log_record_queryset_to_delete()
            .filter(created_at__lte=timezone.now() - timezone.timedelta(days=days))
            .delete()
        )
        deleted_changes = (
            self.get_request_log_change_queryset_to_delete()
            .filter(created_at__lte=timezone.now() - timezone.timedelta(days=days))
            .delete()
        )
        self.stdout.write(f"Удалено записей изменений {deleted_request_records[0]}")
        self.stdout.write(f"Удалено записей изменений {deleted_changes[0]}")

    @classmethod
    def get_request_log_record_queryset_to_delete(cls) -> QuerySet:
        filters = Q()
        for model in cls.get_models_to_keep():
            fields_filter = Q()
            for field in model.permanent_log_fields:
                fields_filter |= Q(changes__fields__icontains=f'"{field}":')
            filters |= Q(changes__instance__icontains=model.__name__) & fields_filter

        return RequestLogRecord.objects.exclude(filters)

    @classmethod
    def get_request_log_change_queryset_to_delete(cls) -> QuerySet:
        filters = Q()
        for model in cls.get_models_to_keep():
            fields_filter = Q()
            for field in model.permanent_log_fields:
                fields_filter |= Q(fields__icontains=f'"{field}":')
            filters |= Q(instance__icontains=model.__name__) & fields_filter

        return RequestLogChange.objects.exclude(filters)

    @staticmethod
    def get_models_to_keep() -> Iterator:
        return filter(lambda model: hasattr(model, "permanent_log_fields"), get_models_to_log())
