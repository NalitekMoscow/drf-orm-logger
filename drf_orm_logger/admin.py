import json
from collections import OrderedDict
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Union

from dateutil.parser import parse
from django.apps import apps
from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.html import escape

from .models import RequestLogChange, RequestLogRecord

if TYPE_CHECKING:
    from django.db import models


def is_date(string):
    try:
        parse(string)
        return True
    except ValueError:
        return False


def get_diff(a, b):
    result = []
    matcher = SequenceMatcher(" \t\n".__contains__, a=a, b=b)
    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode == "equal":
            result.append(matcher.a[i1:i2])
        elif opcode == "replace":
            result.append(
                f'<span class="diff-delete">{matcher.a[i1:i2]}</span>'
                f'<span class="diff-insert">{matcher.b[j1:j2]}</span>'
            )
        elif opcode == "delete":
            result.append(f'<span class="diff-delete">{matcher.a[i1:i2]}</span>')
        elif opcode == "insert":
            result.append(f'<span class="diff-insert">{matcher.b[j1:j2]}</span>')
        else:
            raise TypeError(f"Unknown opcode: {opcode!r}")
    return "".join(result)


def cast_to_str(value: Union[dict, list]):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


class RequestLogChangeModelAdminMixin:
    model = RequestLogChange
    fields = ("change_type", "instance", "changes_table", "record")
    readonly_fields = ("changes_table",)
    inline_classes = ("grp-collapse grp-open",)

    @admin.display(description="Изменения")
    def changes_table(self, instance: RequestLogChange):
        app_label, model_name, pk = instance.instance.split(".")
        model: "models.Model" = apps.get_model(app_label=app_label, model_name=model_name)
        fields = OrderedDict()
        for name in [f.name for f in model._meta.get_fields()]:
            if name not in instance.fields:
                continue
            changes = instance.fields[name]
            old_value, new_value = cast_to_str(changes["old"]), cast_to_str(changes["new"])
            diff = None
            if (
                (isinstance(old_value, str) and isinstance(new_value, str))
                and max(len(old_value), len(new_value)) <= 50000
                and not (is_date(old_value) or is_date(new_value))
            ):
                old_value, new_value = escape(old_value), escape(new_value)
                diff = get_diff(old_value, new_value)
            changes.update({"old": old_value, "new": new_value, "diff": diff})
            fields[name] = changes
        if fields:
            return render_to_string("drf_orm_logger/changes_table.html", {"fields": fields})
        return "-"

    class Media:
        js = ("drf_orm_logger/changes_table.js",)
        css = {"all": ("drf_orm_logger/changes_table.css",)}

class RequestLogChangeModelAdminInline(RequestLogChangeModelAdminMixin, admin.StackedInline):
    pass


class ReadOnlyModelAdminMixin:
    def has_add_permission(self, request, *args, **kwargs):  # noqa
        return False

    def has_change_permission(self, request, *args, **kwargs):  # noqa
        return False

    def has_delete_permission(self, request, *args, **kwargs):  # noqa
        return False


@admin.register(RequestLogRecord)
class RequestLogRecordModelAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ("created_at", "user", "ip", "referer", "method", "status_code", "url")
    list_filter = ("method", "status_code", "user")
    list_select_related = ("user",)
    search_fields = (
        "user__email",
        "user__username",
        "ip",
        "referer",
        "url",
        "changes__instance",
    )
    date_hierarchy = "created_at"

    inlines = (RequestLogChangeModelAdminInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("user")


@admin.register(RequestLogChange)
class RequestLogChangeModelAdmin(admin.ModelAdmin, RequestLogChangeModelAdminMixin):
    pass
