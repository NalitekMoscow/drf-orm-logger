import json
import logging
from copy import deepcopy
from itertools import chain
from typing import Optional, Type

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models.fields.files import FieldFile
from django.db.models.signals import m2m_changed, post_delete, post_init, post_save
from rest_framework.utils.encoders import JSONEncoder

from . import constants
from .middleware import get_request_log
from .models import RequestLogChange
from .utils import compare_states, get_instance_as_dict, get_instance_as_dict_m2m, get_m2m_with_model, instance_to_str

logger = logging.getLogger(__name__)


def object_should_be_logged():
    request_log = get_request_log()
    if request_log is None:
        return settings.REQUESTS_LOGGER_SETTINGS.get("LOG_OBJECTS_OUT_REQUEST", True)
    return (
            settings.REQUESTS_LOGGER_SETTINGS.get("LOG_OBJECTS_IN_REQUEST", True)
            and request_log.request_should_be_logged
    )


class LocalJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, FieldFile):
            return obj.name
        return super().default(obj)


def register_change(instance: models.Model, change_type: str, changed_fields: Optional[dict] = None):
    changes = {
        "change_type": change_type,
        "fields": {},
    }
    if changed_fields:
        encoder = LocalJSONEncoder(ensure_ascii=False)
        encoded_changes = json.loads(encoder.encode(changed_fields))
        for f_name, f_changes in sorted(encoded_changes.items()):
            changes["fields"][f_name] = {
                "label": str(instance._meta.get_field(f_name).verbose_name),
                "old": f_changes["saved"],
                "new": f_changes["current"],
            }
    request_log = get_request_log()
    if request_log:
        previous_log_instance = request_log.requests_logger_changes.get(instance_to_str(instance), None)
    else:
        previous_log_instance = None

    if not previous_log_instance:
        log_instance = RequestLogChange.objects.create(
            change_type=changes["change_type"],
            instance=instance_to_str(instance),
            fields=changes["fields"],
        )
    else:
        log_instance = RequestLogChange.objects.get(id=previous_log_instance)
        log_instance.fields.update(changes["fields"])
        log_instance.save(update_fields=["change_type", "fields"])
    if request_log:
        request_log.requests_logger_changes.setdefault(instance_to_str(instance), log_instance.id)


def update_handler(sender: Type[models.Model], instance: models.Model, **kwargs):  # noqa  # noqa
    try:
        if object_should_be_logged() and instance.pk is not None:
            if kwargs.get("created"):
                instance._original_state = {}
                change_type = constants.CHANGE_TYPE_CREATE
            else:
                change_type = constants.CHANGE_TYPE_UPDATE
            register_change(
                instance=instance,
                change_type=change_type,
                changed_fields=compare_states(get_instance_as_dict(instance), instance._original_state),
            )
    except Exception as e:
        logger.exception(e)


def delete_handler(sender: Type[models.Model], instance: models.Model, **kwargs):  # noqa  # noqa
    try:
        if object_should_be_logged():
            register_change(
                instance=instance,
                change_type=constants.CHANGE_TYPE_DELETE,
                changed_fields=compare_states({}, instance._original_state),
            )
    except Exception as e:
        logger.exception(e)


def m2m_change_handler(sender: Type[models.Model], instance: models.Model, **kwargs):  # noqa
    if not object_should_be_logged():
        return
    if kwargs.get("action") in ("pre_add", "pre_remove"):
        instance._original_m2m_state = get_instance_as_dict_m2m(instance)
    else:
        try:
            register_change(
                instance=instance,
                change_type=constants.CHANGE_TYPE_UPDATE,
                changed_fields=compare_states(get_instance_as_dict_m2m(instance), instance._original_m2m_state),
            )
        except Exception as e:
            logger.exception(e)


def set_original_fields(sender, instance, **kwargs):
    if object_should_be_logged():
        instance._original_state = get_instance_as_dict(instance)


def register_signals():
    for model in get_models_to_log():
        dispatch_uid = f"drf_orm_logger.update_handler({model.__name__})"
        post_init.connect(set_original_fields, sender=model, dispatch_uid=dispatch_uid)
        post_save.connect(update_handler, sender=model, dispatch_uid=dispatch_uid)
        post_delete.connect(delete_handler, sender=model, dispatch_uid=dispatch_uid)
        for field in get_m2m_with_model(model):
            m2m_changed.connect(m2m_change_handler, sender=field[0].remote_field.through, dispatch_uid=dispatch_uid)


def get_models_to_log():
    logger_settings = settings.REQUESTS_LOGGER_SETTINGS
    all_models = deepcopy(apps.all_models)
    for model in logger_settings.get("DISABLED_MODELS", {}):
        app_model = model.lower().split(".")
        if len(app_model) == 2:
            all_models.get(app_model[0], {}).pop(app_model[1], None)
        else:
            all_models.pop(app_model[0], None)
    yield from chain(*([list(value.values()) for value in all_models.values() if value]))
