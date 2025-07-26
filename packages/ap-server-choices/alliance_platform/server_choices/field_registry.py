from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
import types
from typing import Any
from typing import Generic
from typing import TypeVar
from typing import cast

from alliance_platform.core.auth import resolve_perm_name
from alliance_platform.server_choices.settings import ap_server_choices_settings
from django.conf import settings
from django.db.models import Model
from django.db.models import Q
from django.db.models import QuerySet
from django.http import HttpRequest
from django.views import View

# Class currently is anything that can be registered; Serializer, Form, FilterSet

ClassType = TypeVar("ClassType")


@dataclass
class ServerChoiceRegistration(Generic[ClassType]):
    source: ClassType
    fields: dict[str, ServerChoiceFieldRegistration] = field(default_factory=dict)


class ServerChoicesRegistry(Generic[ClassType]):
    # This is for easy lookup by class itself and field name
    server_choices_by_field: dict[tuple[type[ClassType], str], ServerChoiceFieldRegistration]
    # This is for easy lookup using the unique name for a class. The name is what
    # can be passed from the frontend to identify a particular registration
    server_choices_registry: dict[str, ServerChoiceRegistration]
    # The attached ServerChoicesView as returned by ServerChoicesView.as_view(). This is attached automatically
    # when ServerChoicesView.as_view() is called.
    attached_view: View | None = None

    def __init__(self, name):
        """
        Args:
            name: A name for this registration. This is just used to make debugging easier when printing out registration instances.
        """
        self.name = name
        self.server_choices_by_field = {}
        self.server_choices_registry = {}

    def __str__(self):
        return f"ServerChoicesRegistry(name='{self.name}')"


default_server_choices_registry: ServerChoicesRegistry = ServerChoicesRegistry("default")


ServerChoiceRecordTuple = tuple[str | int, str]
ServerChoiceRecordType = Model | ServerChoiceRecordTuple
ServerChoiceRecordsType = QuerySet | Sequence[ServerChoiceRecordTuple]
ServerChoicesType = QuerySet | list[ServerChoiceRecordTuple]


class ServerChoiceFieldRegistration(Generic[ClassType]):
    # The permission to check when returning choices for this backend. This is either a single permission
    # that is checked without access to a record or a list of similar permissions checkable the same way.
    # If you have more complicated use cases override has_perm.
    perm: str | Iterable[str] | Callable[[HttpRequest], bool]
    # Name of the label field returned to the frontend. Used in codegen to tell AsyncChoices what to do
    # Only a single field is supported. This should match what is returned by ``serialize``
    label_field: str
    # Name of the key field returned to the frontend. Used in codegen to tell AsyncChoices what to do. This should
    # match what is returned by ``serialize``
    value_field: str
    # Unique name for class as registered in server_choices_registry
    class_name: str
    field_name: str
    # Default list of fields to search when using the default ``filter_choices`` implementation
    search_fields: list[str] | None
    # The registry this field is attached to
    registry: ServerChoicesRegistry
    # If set choices will include an empty option with this label
    empty_label: str | None
    # If `True` backend API endpoint supports filtering results by search keywords
    supports_server_search: bool
    # The class that this field is attached to. Used in debugging.
    source_class_name: str | None
    #: The number of results returned by the API at a time. Set to 0 to disable pagination (not recommended).
    page_size: int

    def __init__(
        self,
        *,
        field,
        decorated_class: ClassType,
        class_name: str,
        field_name: str,
        search_fields: list[str] | None = None,
        perm=None,
        page_size=None,
        get_choices=None,
        get_record=None,
        get_records=None,
        get_label=None,
        filter_choices=None,
        model=None,
        label_field="label",
        value_field="key",
        empty_label=None,
        serialize=None,
        supports_server_search=None,
        source_class_name=None,
    ):
        if supports_server_search is None:
            supports_server_search = bool(search_fields)
        self.empty_label = empty_label
        self.supports_server_search = supports_server_search
        # In debug expose the class name. In production we have so far avoided exposing any underlying
        # implementation details such as the module or class name - so just expose the generated name
        # that could be used for debugging with a bit more effort.
        self.source_class_name = source_class_name if settings.DEBUG else class_name
        # Note: mypy doesn't like shadowing methods on an object so there are a lot of ignores here
        # see discussion here: https://github.com/python/mypy/issues/2427
        if (
            get_choices is not None
        ):  # for potential QuerySets, do not use "if get_choices:" test as that will run the query on spot
            if isinstance(get_choices, QuerySet):
                # If a QuerySet is passed that is the choices to use
                self.get_choices = lambda request: get_choices  # type: ignore[method-assign]
            else:
                self.get_choices = types.MethodType(get_choices, self)  # type: ignore[method-assign]
        if get_record:
            self.get_record = types.MethodType(get_record, self)  # type: ignore[method-assign]
        if get_records:
            self.get_records = types.MethodType(get_records, self)  # type: ignore[method-assign]
        if filter_choices:
            self.filter_choices = types.MethodType(filter_choices, self)  # type: ignore[method-assign]
        if serialize:
            self.serialize = types.MethodType(serialize, self)  # type: ignore[method-assign]
        if get_label:
            self.get_label = types.MethodType(get_label, self)  # type: ignore[method-assign]
        self.search_fields = search_fields
        self.field = field
        self._perms = None
        if perm is None and model:
            # If no perm is specified default to inferring it from the Model. If user
            # has create permission then we assume they have permission to list related
            # records for the model
            perm = resolve_perm_name(
                entity=model,
                action="create",
                is_global=True,
            )
        elif perm is None:
            raise ValueError(
                "You must specify 'perm' when 'model' is not passed for Server Choices %s" % class_name
            )
        self.page_size = ap_server_choices_settings.PAGE_SIZE if page_size is None else page_size
        self.perm = perm
        self.class_name = class_name
        self.field_name = field_name
        self.label_field = label_field
        self.value_field = value_field

    def is_paginated(self):
        return self.page_size != 0

    def has_perm(self, request: HttpRequest):
        if callable(self.perm):
            return self.perm(request)
        elif hasattr(request, "user"):
            if isinstance(self.perm, str):
                return request.user.has_perm(self.perm)
            elif isinstance(self.perm, Iterable):
                return request.user.has_perms(self.perm)
            else:
                raise ValueError(
                    "'perm' passed to ServerChoiceFieldRegistration must be either a string, "
                    "an iterable of strings, or a function that takes a request and returns a bool"
                )
        else:
            raise AttributeError(
                "'perm' is not a callable and there is no user associated with the request - can't check permissions"
            )

    def serialize(
        self,
        item_or_items: ServerChoiceRecordsType | ServerChoiceRecordType,
        request: HttpRequest,
    ) -> list | dict:
        """Serialize the specified item(s)

        Must handle either 1 item or an iterable of items

        The default implementation returns a list of dicts with a key and label field named according to
        self.value_field and self.label_field.

        - If an iterable of Model is passed then the key is set to ``.pk`` and label to the ``__str__()``
        - If an iterable of 2-tuples is passed then the first element is used as key and second as label (eg. standard field choices in django)
        """
        if isinstance(item_or_items, Model):
            return {
                self.value_field: item_or_items.pk,
                self.label_field: self.get_label(item_or_items),
            }

        if len(item_or_items) == 0:
            return []

        # Single (key, label) pair
        if isinstance(item_or_items, tuple):
            return {
                self.value_field: item_or_items[0],
                self.label_field: self.get_label(cast(ServerChoiceRecordType, item_or_items)),
            }

        # List of (key, label) pairs
        items = list(item_or_items)
        if isinstance(items[0], tuple):
            return [
                {self.value_field: key, self.label_field: self.get_label((key, label))}
                for key, label in item_or_items
            ]

        # List of records
        return [
            {self.value_field: record.pk, self.label_field: self.get_label(record)}
            for record in cast(Iterable[Model], item_or_items)
        ]

    def get_choices(self, request: HttpRequest) -> ServerChoicesType:
        raise NotImplementedError

    def get_record(self, pk: str, request: HttpRequest) -> ServerChoiceRecordType:
        raise NotImplementedError

    def get_records(self, pks: list[str], request: HttpRequest) -> ServerChoiceRecordsType:
        raise NotImplementedError

    def get_label(self, record: ServerChoiceRecordType) -> str:
        # This is (key, label)
        if isinstance(record, (list, tuple)):
            return record[1]
        return str(record)

    def filter_choices(self, choices: ServerChoicesType, request: HttpRequest) -> ServerChoicesType:
        """Given some choices returned by ``get_choices``, filter then based on current request.

        Default implementation works as follows

        1) Looks for search terms in the 'keywords' query param. This is split into individual words and each
           word must exist somewhere in the fields searched.
        2) If choices is a QuerySet and ``search_fields`` is set then each of those fields is filtered and OR'd
        3) If choices is a QuerySet and ``search_fields`` is not set then it is an error
        4) If choices is a list of key/label tuples then each label is searched with the keywords
        """
        keywords = request.GET.get("keywords")
        if keywords:
            if isinstance(choices, QuerySet):
                if not self.search_fields:
                    raise ValueError(
                        "You must provide either `search_fields` or `filter_choices` to support backend filtering for Server Choices for %s"
                        % self.class_name
                    )
                qs_filter = Q()
                for keyword in filter(bool, keywords.split(" ")):
                    keyword_filter = Q()
                    for field_name in self.search_fields:
                        keyword_filter |= Q(**{field_name + "__icontains": keyword})
                    qs_filter &= keyword_filter
                return choices.filter(qs_filter)
            matched_choices = []
            keyword_list = [keyword.lower() for keyword in filter(bool, keywords.split(" "))]
            for key, label in choices:
                if all([keyword in label.lower() for keyword in keyword_list]):
                    matched_choices.append((key, label))
            return matched_choices
        return choices

    @classmethod
    def get_available_fields(cls, decorated_cls: ClassType) -> dict[str, Any]:
        """Return the available fields on :code:`decorated_cls`. Should return a dict mapping field_name to field instance"""
        raise NotImplementedError

    @classmethod
    def infer_fields(cls, field_mapping: dict[str, Any]) -> Iterable[str]:
        """Given :code:`field_mapping` return the names of the fields that should have choices generated for them

        This is only used when no explicit list of fields is provided"""
        raise NotImplementedError

    @classmethod
    def should_handle_class_for_registration(cls, decorated_class: ClassType) -> bool:
        """Given the class to which the server_choices decorator is applied, determine
        whether this registration class should be used to handle it. Will be called
        by :class:`~alliance_platform.server_choices.class_handlers.registry.ClassHandlersRegistry`
        """
        raise NotImplementedError
