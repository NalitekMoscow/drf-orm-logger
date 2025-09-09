from django.apps import AppConfig


class RequestsLoggerConfig(AppConfig):
    name = "drf_orm_logger"
    verbose_name = "Лог http-запросов"

    def ready(self):
        from .signals import register_signals

        register_signals()
