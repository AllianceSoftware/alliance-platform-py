from collections.abc import Callable
from collections.abc import Iterable
import hashlib
import warnings

from alliance_platform.server_choices.class_handlers.registry import ClassHandlerRegistry
from alliance_platform.server_choices.class_handlers.registry import default_class_handler_registry
from alliance_platform.server_choices.field_registry import ServerChoiceFieldRegistration
from alliance_platform.server_choices.field_registry import ServerChoiceRecordsType
from alliance_platform.server_choices.field_registry import ServerChoiceRecordType
from alliance_platform.server_choices.field_registry import ServerChoiceRegistration
from alliance_platform.server_choices.field_registry import ServerChoicesRegistry
from alliance_platform.server_choices.field_registry import ServerChoicesType
from alliance_platform.server_choices.field_registry import default_server_choices_registry
from django.core.exceptions import ImproperlyConfigured
from django.db.models import QuerySet
from django.http import HttpRequest

GetChoicesCallableType = Callable[[ServerChoiceFieldRegistration, HttpRequest], ServerChoicesType]


def server_choices(
    fields: Iterable[str] | None = None,
    *,
    registration_class: type[ServerChoiceFieldRegistration] | None = None,
    registry: ServerChoicesRegistry = default_server_choices_registry,
    class_handler_registry: ClassHandlerRegistry = default_class_handler_registry,
    search_fields: list[str] | None = None,
    perm: str | Iterable[str] | Callable[[HttpRequest], bool] | None = None,
    page_size: int | None = None,
    get_choices: QuerySet | GetChoicesCallableType | None = None,
    get_record: Callable[[ServerChoiceFieldRegistration, str, HttpRequest], ServerChoiceRecordType]
    | None = None,
    get_records: (
        Callable[[ServerChoiceFieldRegistration, list[str], HttpRequest], ServerChoiceRecordsType] | None
    ) = None,
    get_label: Callable[[ServerChoiceFieldRegistration, ServerChoiceRecordType], str] | None = None,
    filter_choices: (
        Callable[[ServerChoiceFieldRegistration, ServerChoicesType, HttpRequest], ServerChoicesType] | None
    ) = None,
    label_field: str | None = "label",
    value_field: str | None = "key",
    serialize: (
        Callable[[ServerChoiceRecordsType | ServerChoiceRecordType, HttpRequest], list | dict] | None
    ) = None,
    **kwargs,
):
    """Decorate a class and expose a API endpoint to lookup choices for a field

    The most common use case for this is to provide AJAX lookups for autocomplete widgets.

    For instance:

    * On a `Serializer <https://www.django-rest-framework.org/api-guide/serializers/#serializers>`_ class expose the choices for a `PrimaryKeyRelatedField <https://www.django-rest-framework.org/api-guide/relations/#primarykeyrelatedfield>`_
    * On a django :class:`~django.forms.Form` expose choices for a :class:`~django.forms.ModelChoiceField`
    * On a :class:`~django_filters.filterset.FilterSet` expose choices for a :class:`~django_filters.filterset.ModelChoiceFilter`

    If :code:`fields` isn't specified creates choices using the :meth:`registration_class.infer_fields <alliance_platform.server_choices.register.ServerChoiceFieldRegistration.infer_fields>` static method. For
    a :code:`Serializer` this takes all related fields, for a :code:`Form` & :code:`FilterSet` all :code:`ModelChoiceField`.

    The examples above all use to related fields as these can have a large a variable size list of choices - but any field
    with choices can be used with the same interface. For example if you had a very large static list
    of options that you wanted to serve dynamically with backend filtering & pagination ``server_choices``
    can be used.

    See the :doc:`usage documentation </usage>` for more details and examples.

    **Base Usage**

    .. code:: python

        # This example applies to  a serializer class but the same usage applies to both
        # Forms and FilterSets

        # Register 2 fields and use the ``name`` field on them all when doing filtering
        @server_choices(["trading_entity", "waste_types"], search_fields=["name"])
        # Register project_status but don't do pagination
        @server_choices(["project_status"], page_size=0)
        # Register project_manager but override how choices are returned
        @server_choices(["project_manager", get_choices=get_project_manager_choices]
        class ProjectSerializer(ModelSerializer):
            ...

    Args:
        fields: List of fields to support. If not specified creates choices for all related fields on the serializer.
        registration_class: The class to use for registration
        registry: The registry in which to register the supported fields.
        class_handler_registry: The registry to search for a handler for the decorated class
        label_field: What to name the label field on the serialized object (defaults to "label"). If you override ``serialize`` this may be ignored.
        value_field: What to name the value field on the serialized object (defaults to "key"). If you override ``serialize`` this may be ignored.
        search_fields: A list of fields to use in default filtering. Each field will be searched using ``icontains`` and OR'd together. For more complicated filtering pass ``filter_choices``
        perm: The permission name to check when accessing choices for this field. See :class:`~alliance_platform.server_choices.views.ServerChoicesView`. If not specified uses :meth:`~django_site_core.auth.resolve_perm_name` with action of ``create`` (we
            default to 'create' on the model the relation is _from_ as otherwise you'd be prevented from saving the record at all). The ``perm`` can only be inferred when using
            a ``ModelSerializer``, ``ModelForm`` or ``FilterSet``. If using a plain ``Serializer`` or ``Form`` you must provide ``perm``.
            A list can also be provided in which case all perms listed would be checked (ie. like ``permission_required``)
        page_size: The number of results to return in each API call. Defaults to 20. If set to ``0`` then no pagination is used.
        get_choices: Override how choices are generated. Passed this instance and the current request. This can return any iterable (eg. a queryset, list of key/value tuples)
        get_record: Override how a single record is looked up. Passed this instance, the pk of record to return and the current request. Note that no individual permission checks are done - ``perm`` is checked once by default.
        get_records: Override how a multiple records are looked up. Passed this instance, a list of pks to return and the current request. Note that no individual permission checks are done - ``perm`` is checked once by default.
        get_label: Override how the label for a record is returned. By default just calls ``str`` on the record. Note that this will also be called
            if the choices is a list of tuple and will receive the tuple representation of a choice (eg. :code:`(key, label)`)
        filter_choices: Override how choices are filtered. Passed this instance, the choices to filter and the current request.
        serialize: Override how record(s) are serialized. Passed this instance, the item or items to serialize, and the current request. Where possible use
            self.label_field and self.value_field as the name of the fields on returned data (if applicable - if using a complete custom return shape then ignore). This
            allows codegen to generate frontend code that knows what to expect from :class:`~alliance_platform.server_choices.views.ServerChoicesView`.
        empty_label: Label to use for empty option. Specify ``None`` to disable the empty option. This will be inferred from the field if possible otherwise will be ``None``.
        **kwargs: Any extra kwargs are passed through directly to :code:`registration_class`
    """

    def wrapper(cls):
        _registration_class = registration_class
        if registration_class is None:
            for class_handler in class_handler_registry.registered_handlers[::-1]:
                if class_handler.should_handle_class_for_registration(cls):
                    _registration_class = class_handler
                    break

        if not _registration_class:
            raise ImproperlyConfigured(
                f"Unable to infer registration_class to use for {cls}. Specify 'registration_class' manually to resolve."
            )

        field_mapping = _registration_class.get_available_fields(cls)
        _name = hashlib.sha1(f"{cls.__module__}.{cls.__name__}".encode("utf8")).hexdigest()
        if _name not in registry.server_choices_registry:
            registry.server_choices_registry[_name] = ServerChoiceRegistration(cls)
        _fields = fields
        if _fields is None:
            _fields = _registration_class.infer_fields(field_mapping)
        unknown_fields = []
        for field_name in _fields:
            if field_name not in field_mapping:
                unknown_fields.append(field_name)
                continue
            if field_name in registry.server_choices_registry[_name].fields:
                warnings.warn(f"Field {field_name} already registered")

            field = field_mapping[field_name]
            registration = _registration_class(
                decorated_class=cls,
                field=field,
                source_class_name=f"{cls.__module__}.{cls.__name__}",
                class_name=_name,
                field_name=field_name,
                search_fields=search_fields,
                perm=perm,
                page_size=page_size,
                get_choices=get_choices,
                get_record=get_record,
                get_records=get_records,
                get_label=get_label,
                filter_choices=filter_choices,
                label_field=label_field,
                value_field=value_field,
                serialize=serialize,
                **kwargs,
            )
            registration.registry = registry
            registry.server_choices_registry[_name].fields[field_name] = registration
            registry.server_choices_by_field[(cls, field_name)] = registration
        if unknown_fields:
            raise ImproperlyConfigured(f"The field(s) {', '.join(unknown_fields)} do not exist on {cls}")
        return cls

    return wrapper
