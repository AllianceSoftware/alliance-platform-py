from __future__ import annotations

from collections.abc import Iterable

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.http import HttpRequest
from rest_framework import serializers
from rest_framework.relations import ManyRelatedField
from rest_framework.relations import RelatedField

from ..field_registry import ServerChoiceFieldRegistration
from ..field_registry import ServerChoiceRecordsType
from ..field_registry import ServerChoiceRecordType
from ..field_registry import ServerChoicesType


class SerializerServerChoiceFieldRegistration(ServerChoiceFieldRegistration):
    """Registration for DRF Serializer classes

    You usually don't need to instantiate this manually - call :meth:`~alliance_platform.server_choices.server_choices` instead

    Args:
        serializer: The serializer this registration is for
        field: The field on ``serializer`` this registration is for
        class_name: The registered class name. This is used to index into ``server_choices_registry``
        field_name: The name of the field
        **kwargs: See :class:`~alliance_platform.server_choices.register.ServerChoiceFieldRegistration`
    """

    def __init__(
        self,
        *,
        decorated_class: type[serializers.Serializer],
        perm=None,
        **kwargs,
    ):
        model = None
        if issubclass(decorated_class, serializers.ModelSerializer):
            model = decorated_class.Meta.model
        elif perm is None:
            raise ValueError("You must specify 'perm' when not using a ModelSerializer")

        super().__init__(perm=perm, model=model, decorated_class=decorated_class, **kwargs)

    def get_choices(self, request: HttpRequest) -> ServerChoicesType:
        """Return the available choices for this field. Can return a queryset or list of key/label tuples."""
        if isinstance(self.field, ManyRelatedField):
            return self.field.child_relation.get_queryset()
        if hasattr(self.field, "get_queryset"):
            return self.field.get_queryset()
        if hasattr(self.field, "choices"):
            return list(self.field.choices.items())
        raise ValueError("Cannot work out choices for field - pass get_choices")

    def get_record(self, pk: str, request: HttpRequest) -> ServerChoiceRecordType:
        """Return the matching record for the specified primary key.

        Raises ObjectDoesNotExist if not found
        """
        choices = self.get_choices(request)
        if isinstance(choices, QuerySet):
            return choices.get(pk=pk)
        for key, value in choices:
            if str(key) == str(pk):
                return (key, value)
        raise ObjectDoesNotExist()

    def get_records(self, pks: list[str], request: HttpRequest) -> ServerChoiceRecordsType:
        """Return the matching records for the specified primary keys.

        If any record is not found it is omitted from the return value.
        """
        if isinstance(self.field, ManyRelatedField):
            return self.field.child_relation.get_queryset().filter(pk__in=pks)
        choices = self.get_choices(request)
        if isinstance(choices, QuerySet):
            return choices.filter(pk__in=pks)
        matches = []
        for key, value in choices:
            if str(key) in [str(x) for x in pks]:
                matches.append((key, value))
        return matches

    @classmethod
    def get_available_fields(cls, serializer_cls):
        return serializer_cls().get_fields()

    @classmethod
    def infer_fields(cls, field_mapping) -> Iterable[str]:
        for field_name, field in field_mapping.items():
            if isinstance(field, (RelatedField, ManyRelatedField)):
                yield field_name

    @classmethod
    def should_handle_class_for_registration(cls, decorated_class):
        return issubclass(decorated_class, serializers.Serializer)
