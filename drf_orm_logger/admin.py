import json
from collections import OrderedDict
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Union
from datetime import timedelta, date, datetime, time
from dateutil.parser import parse
from django.apps import apps
from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.html import escape
from django.utils import timezone
from django.shortcuts import redirect

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


def week_start_for(d: date) -> date:
    # понедельник (iso Monday=1)
    return d - timedelta(days=d.isoweekday() - 1)

class WeekListFilter(admin.SimpleListFilter):
    title = "неделя"
    parameter_name = "week"

    def lookups(self, request, model_admin):
        qs = model_admin.get_queryset(request)
        dates = qs.dates("created_at", "week", order="DESC")
        lookups = []
        for d in dates:
            week_start = d                 # понедельник
            week_end = d + timedelta(days=6)
            label = f"{week_start.strftime('%d.%m.%Y')} – {week_end.strftime('%d.%m.%Y')}"
            lookups.append((week_start.isoformat(), label))
        return lookups

    def queryset(self, request, queryset):
        if self.value():
            start = date.fromisoformat(self.value())
            end = start + timedelta(days=7)

            # индекс-дружелюбно: aware и полуоткрытый интервал [start; end)
            start_dt = timezone.make_aware(datetime.combine(start, time.min))
            end_dt   = timezone.make_aware(datetime.combine(end,   time.min))
            return queryset.filter(created_at__gte=start_dt, created_at__lt=end_dt)
        return queryset


class DateRedirectMixin:
    show_full_result_count = False
    def changelist_view(self, request, extra_context=None):
        if "week" not in request.GET:
            today = timezone.localdate()
            ws = week_start_for(today).isoformat()
            params = request.GET.copy()
            params["week"] = ws
            for k in list(params.keys()):
                if k.startswith("created_at__"):
                    params.pop(k, None)
            return redirect(f"{request.path}?{params.urlencode()}")

        return super().changelist_view(request, extra_context=extra_context)


@admin.register(RequestLogRecord)
class RequestLogRecordModelAdmin(DateRedirectMixin, ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ("created_at", "user", "ip", "referer", "method", "status_code", "url")
    list_filter = (WeekListFilter, "method", "status_code", "user")
    list_select_related = ("user",)
    search_fields = (
        "user__email",
        "user__username",
        "ip",
        "referer",
        "url",
        "changes__instance",
    )
    inlines = (RequestLogChangeModelAdminInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("user")


@admin.register(RequestLogChange)
class RequestLogChangeModelAdmin(DateRedirectMixin, admin.ModelAdmin, RequestLogChangeModelAdminMixin):
    list_filter = (WeekListFilter,)
