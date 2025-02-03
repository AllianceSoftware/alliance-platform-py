from collections.abc import Callable
from collections.abc import Iterable
import hashlib
import warnings

from alliance_platform.server_choices.form import FilterSetServerChoiceFieldRegistration
from alliance_platform.server_choices.form import FormServerChoiceFieldRegistration
from alliance_platform.server_choices.register import ServerChoiceFieldRegistration
from alliance_platform.server_choices.register import ServerChoiceRecordsType
from alliance_platform.server_choices.register import ServerChoiceRecordType
from alliance_platform.server_choices.register import ServerChoiceRegistration
from alliance_platform.server_choices.register import ServerChoicesRegistry
from alliance_platform.server_choices.register import ServerChoicesType
from alliance_platform.server_choices.register import default_server_choices_registry
from alliance_platform.server_choices.serializer import SerializerServerChoiceFieldRegistration
from django.core.exceptions import ImproperlyConfigured
from django.db.models import QuerySet
from django.forms import BaseForm
from django_filters import FilterSet
from rest_framework import serializers
from rest_framework.pagination import BasePagination
from rest_framework.request import Request
from rest_framework.settings import api_settings

GetChoicesCallableType = Callable[[ServerChoiceFieldRegistration, Request], ServerChoicesType]


def server_choices(
    fields: Iterable[str] | None = None,
    *,
    registration_class: type[ServerChoiceFieldRegistration] | None = None,
    registry: ServerChoicesRegistry = default_server_choices_registry,
    search_fields: list[str] | None = None,
    perm: str | Iterable[str] | Callable[[Request], bool] | None = None,
    pagination_class: str | type[BasePagination] | None = api_settings.DEFAULT_PAGINATION_CLASS,
    get_choices: QuerySet | GetChoicesCallableType | None = None,
    get_record: Callable[[ServerChoiceFieldRegistration, str, Request], ServerChoiceRecordType] | None = None,
    get_records: (
        Callable[[ServerChoiceFieldRegistration, list[str], Request], ServerChoiceRecordsType] | None
    ) = None,
    get_label: Callable[[ServerChoiceFieldRegistration, ServerChoiceRecordType], str] | None = None,
    filter_choices: (
        Callable[[ServerChoiceFieldRegistration, ServerChoicesType, Request], ServerChoicesType] | None
    ) = None,
    label_field: str | None = "label",
    value_field: str | None = "key",
    serialize: (
        Callable[[ServerChoiceRecordsType | ServerChoiceRecordType, Request], list | dict] | None
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

    **Data Returned**

    :class:`~alliance_platform.server_choices.views.ServerChoicesView` (see **API Endpoint** below) will return only the key
    and a label for each record that is returned. The label, by default, is the string representation of the object.
    To change this you can pass :code:`get_label`. Note that if choices is not a queryset then the item passed to
    ``get_label`` will be a 2-tuple of ``key`` and ``label``. eg. The default ``get_label`` looks like:

    .. code:: python

        def get_label(registration, record):
            if isinstance(record, (list, tuple)):
                return record[1]
            return str(record)

    **Permissions**

    When the endpoint is used to get the available choices permission checks apply. You can control what permission is
    used by passing the :code:`perm` kwarg. If not specified and the django Model can be inferred from the decorated
    class (eg. when using a :class:`~rest_framework.serializers.ModelSerializer`, :class:`~django.forms.ModelForm` or
    :class:`~django_filters.filterset.FilterSet`) then the :code:`create` permission for that model as returned by
    :meth:`~django_site_core.auth.resolve_perm_name` will be used.

    For example if you had a :code:`ModelForm` for the model :code:`User` which had foreign keys to :code:`Address`
    and :code:`Group` then the choices for both models would be the :code:`create` permission on :code:`User`. The
    rationale for this is if you weren't using server_choices and rendering the form directly there would be no specific
    check on the foreign key form fields - all the options would be embedded directly in the returned HTML. Using
    :code:`create` means if you can create the main record you can see the options for each field you need to save on
    that record. Note that the only information exposed about the related is the :code:`pk` and a label for it - you
    can't access all the data from it.


    **API Endpoint**

    Once decorated the the following applies:

    1. :class:`~alliance_platform.server_choices.views.ServerChoicesView` will serve up the choices for this registration based on the registered name and field.
       Permissions are checked according to the ``perm`` property. See :class:`~alliance_platform.server_choices.register.ServerChoiceFieldRegistration` for
       more details.

    2. Presto codegen will use this registrations when creating the base ViewModel classes for classes decorated with
       :meth:`~codegen.presto.decorator.view_model_codegen`

    In order for :class:`~alliance_platform.server_choices.views.ServerChoicesView` to know what to return a unique name is
    generated as part of the registration for the class being registered. This is hashed to avoid exposing application
    structure to the frontend. This name, along with the specific field name on that class, is passed when calling
    :class:`~alliance_platform.server_choices.views.ServerChoicesView` which it then uses to look up in the global registry to
    get the relevant registration instance.

    **Usage**

    .. code:: python

        # This example applies to  a serializer class but the same usage applies to both
        # Forms and FilterSets

        # Register 2 fields and use the ``name`` field on them all when doing filtering
        @server_choices(["trading_entity", "waste_types"], search_fields=["name"])
        # Register project_status but don't do pagination
        @server_choices(["project_status"], pagination_class=None)
        # Register project_manager but override how choices are returned
        @server_choices(["project_manager", get_choices=get_project_manager_choices]
        class ProjectSerializer(ModelSerializer):
            ...

    Args:
        fields: List of fields to support. If not specified creates choices for all related fields on the serializer.
        registration_class: The class to use for registration
        registry: The registry to use for registration.
        label_field: What to name the label field on the serialized object (defaults to "label"). If you override ``serialize`` this may be ignored.
        value_field: What to name the value field on the serialized object (defaults to "key"). If you override ``serialize`` this may be ignored.
        search_fields: A list of fields to use in default filtering. Each field will be searched using ``icontains`` and OR'd together. For more complicated filtering pass ``filter_choices``
        perm: The permission name to check when accessing choices for this field. See :class:`~alliance_platform.server_choices.views.ServerChoicesView`. If not specified uses :meth:`~django_site_core.auth.resolve_perm_name` with action of ``create`` (we
            default to 'create' on the model the relation is _from_ as otherwise you'd be prevented from saving the record at all). The ``perm`` can only be inferred when using
            a ``ModelSerializer``, ``ModelForm`` or ``FilterSet``. If using a plain ``Serializer`` or ``Form`` you must provide ``perm``.
            A list can also be provided in which case all perms listed would be checked (ie. like ``permission_required``)
        pagination_class: The pagination class to use. Defaults to the DRF default. Set to ``None`` to disable pagination.
        get_choices: Override how choices are generated. Passed this instance and the current DRF request. This can return any iterable (eg. a queryset, list of key/value tuples)
        get_record: Override how a single record is looked up. Passed this instance, the pk of record to return and the current DRF request. Note that no individual permission checks are done - ``perm`` is checked once by default.
        get_records: Override how a multiple records are looked up. Passed this instance, a list of pks to return and the current DRF request. Note that no individual permission checks are done - ``perm`` is checked once by default.
        get_label: Override how the label for a record is returned. By default just calls ``str`` on the record. Note that this will also be called
            if the choices is a list of tuple and will receive the tuple representation of a choice (eg. :code:`(key, label)`)
        filter_choices: Override how choices are filtered. Passed this instance, the choices to filter and the current DRF request.
        serialize: Override how record(s) are serialized. Passed this instance, the item or items to serialize, and the current DRF request. Where possible use
            self.label_field and self.value_field as the name of the fields on returned data (if applicable - if using a complete custom return shape then ignore). This
            allows codegen to generate frontend code that knows what to expect from :class:`~alliance_platform.server_choices.views.ServerChoicesView`.
        empty_label: Label to use for empty option. Specify ``None`` to disable the empty option. This will be inferred from the field if possible otherwise will be ``None``.
        **kwargs: Any extra kwargs are passed through directly to :code:`registration_class`
    """

    def wrapper(cls):
        _registration_class = registration_class
        specialized_kwargs = {}
        if registration_class is None:
            if issubclass(cls, serializers.Serializer):
                _registration_class = SerializerServerChoiceFieldRegistration
                specialized_kwargs = {"serializer": cls}
            elif issubclass(cls, BaseForm):
                _registration_class = FormServerChoiceFieldRegistration
                specialized_kwargs = {"form_cls": cls}
            elif issubclass(cls, FilterSet):
                _registration_class = FilterSetServerChoiceFieldRegistration
                specialized_kwargs = {"filterset_cls": cls}

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
                **specialized_kwargs,
                field=field,
                source_class_name=f"{cls.__module__}.{cls.__name__}",
                class_name=_name,
                field_name=field_name,
                search_fields=search_fields,
                perm=perm,
                pagination_class=pagination_class,
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
