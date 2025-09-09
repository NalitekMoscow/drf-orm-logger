from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.db import models

from . import constants

User = get_user_model()


class RequestLogRecord(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата", db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="+", null=True, verbose_name="Пользователь")
    ip = models.GenericIPAddressField(verbose_name="IP")
    method = models.CharField(max_length=7, verbose_name="Метод")
    referer = models.CharField(max_length=1000, verbose_name="Источник")
    url = models.CharField(max_length=1000, verbose_name="Адрес")
    status_code = models.PositiveSmallIntegerField(verbose_name="Код ответа")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Запись"
        verbose_name_plural = "Записи"

    def __str__(self):
        return (
            f'[{self.created_at.isoformat(" ")}] '
            f"{self.user_id} "
            f"{self.referer} "
            f"{self.ip} "
            f"{self.method} "
            f"{self.status_code} "
            f"{self.url}"
        )


class RequestLogChange(models.Model):
    CHANGE_TYPE_CHOICES = OrderedDict(
        (
            (constants.CHANGE_TYPE_CREATE, "Создано"),
            (constants.CHANGE_TYPE_UPDATE, "Изменено"),
            (constants.CHANGE_TYPE_DELETE, "Удалено"),
        )
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата", db_index=True)
    record = models.ForeignKey(
        RequestLogRecord, on_delete=models.CASCADE, related_name="changes", verbose_name="Запись", null=True
    )
    change_type = models.CharField(
        max_length=max(len(k) for k, v in CHANGE_TYPE_CHOICES.items()),
        choices=CHANGE_TYPE_CHOICES.items(),
        verbose_name="Тип",
    )
    instance = models.CharField(max_length=200, verbose_name="Объект", db_index=True)
    fields = models.JSONField(blank=True, null=True, verbose_name="Изменённые поля")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Изменение"
        verbose_name_plural = "Изменения"

    def __str__(self):
        return f'[{self.created_at.isoformat(" ")}] ' f"{self.change_type} " f"{self.instance}"


class RequestLogChangeAdmin(RequestLogChange):
    class Meta:
        proxy = True
        managed = False
        ordering = ("-created_at",)
        verbose_name = "Изменение"
        verbose_name_plural = "Изменения"

    def __str__(self):
        return ""
