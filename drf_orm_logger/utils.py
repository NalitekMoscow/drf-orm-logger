from copy import deepcopy

from django.core.files import File
from django.db import models
from django.db.models.expressions import BaseExpression, Combinable
from rest_framework.exceptions import ValidationError


def instance_to_str(instance: "models.Model") -> str:
    return f"{instance._meta.app_label}.{instance._meta.object_name}.{instance.pk}"


def get_instance_as_dict(instance):
    all_field = {}

    deferred_fields = instance.get_deferred_fields()

    for field in instance._meta.concrete_fields:
        if field.get_attname() in deferred_fields:
            continue

        field_value = getattr(instance, field.attname)

        if isinstance(field_value, File):
            field_value = field_value.name

        if isinstance(field_value, (BaseExpression, Combinable)):
            continue

        try:
            field_value = field.to_python(field_value)
        except ValidationError:
            pass

        if isinstance(field_value, memoryview):
            field_value = bytes(field_value)

        all_field[field.name] = deepcopy(field_value)

    return all_field


def compare_states(new_state, original_state):
    modified_field = {}

    # Кейс, когда новое состояние отсутствует, то есть объект удален
    if not new_state:
        for key, value in original_state.items():
            if value is None:
                continue
            modified_field[key] = {"saved": value, "current": None}
        return modified_field

    # Кейс, когда старое состояние отсутствует, то есть объект создан
    if not original_state:
        for key, value in new_state.items():
            if value is None:
                continue
            modified_field[key] = {"saved": None, "current": value}
        return modified_field

    # Кейс, когда у объекта есть и новое и старое состояние, то есть объект изменен
    for key, value in new_state.items():
        try:
            original_value = original_state[key]
        except KeyError:
            continue

        if original_value == value:
            continue

        modified_field[key] = {"saved": original_value, "current": value}

    return modified_field


def get_m2m_with_model(model):
    return [
        (f, f.model if f.model != model else None)
        for f in model._meta.get_fields()
        if f.many_to_many and not f.auto_created
    ]


def get_instance_as_dict_m2m(instance):
    m2m_fields = {}

    if instance.pk:
        for f, _ in get_m2m_with_model(instance.__class__):
            m2m_fields[f.attname] = {obj.pk for obj in getattr(instance, f.attname).all()}

    return m2m_fields
