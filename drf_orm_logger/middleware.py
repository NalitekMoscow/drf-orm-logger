import dataclasses
import logging
import threading
from copy import deepcopy
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from rest_framework.permissions import SAFE_METHODS

from .models import RequestLogChange, RequestLogRecord

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


GLOBAL_LOG_STORE = threading.local()


@dataclasses.dataclass
class LogStore:
    requests_logger_changes: dict = dataclasses.field(default_factory=lambda: {})
    request_should_be_logged: bool = False


def get_client_ip(request: "HttpRequest"):
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0]
    return request.META.get("REMOTE_ADDR")


class RequestsLoggerMiddleware(MiddlewareMixin):
    def process_request(self, request):  # noqa
        GLOBAL_LOG_STORE.request_log = LogStore(request_should_be_logged=False)
        if request.method.upper() not in SAFE_METHODS:
            intercept_func = getattr(settings, "REQUESTS_LOGGER_SETTINGS", {}).get("INTERCEPT_FUNC", lambda args: True)
            if not callable(intercept_func) or intercept_func(request):
                GLOBAL_LOG_STORE.request_log.request_should_be_logged = getattr(
                    settings, "REQUESTS_LOGGER_SETTINGS", {}
                ).get("LOG_REQUEST", True)

    def process_response(self, request: "HttpRequest", response: "HttpResponse"):  # noqa
        if (request_log := deepcopy(get_request_log())) and request_log.request_should_be_logged:
            try:
                referer = request.headers.get("Referer") or request.headers.get("Origin")
                url = request.get_full_path()
                record = RequestLogRecord.objects.create(
                    user=request.user if (request.user.is_authenticated and getattr(request.user, 'pk', None)) else None,
                    method=request.method,
                    referer=referer[:1000] if referer else "",
                    url=url[:1000],
                    ip=get_client_ip(request),
                    status_code=response.status_code,
                )
                RequestLogChange.objects.filter(id__in=list(request_log.requests_logger_changes.values())).update(
                    record=record
                )
            except Exception as e:
                logger.exception(e)
        delete_request_log()
        return response


def get_request_log():
    try:
        return GLOBAL_LOG_STORE.request_log
    except AttributeError:
        return None


def delete_request_log():
    try:
        del GLOBAL_LOG_STORE.request_log
    except AttributeError:
        return None
