from collections.abc import MutableSequence
from typing import Any
from typing import Protocol
from typing import cast

from allianceutils.util import underscoreize
from django.core.exceptions import ObjectDoesNotExist
from django_filters.rest_framework import BooleanFilter
from django_filters.rest_framework import FilterSet
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .register import default_server_choices_registry


class APIViewProtocol(Protocol):
    initkwargs: dict[str, Any]  # drf-stubs is missing this


class ServerChoicesInputSerializer(serializers.Serializer):
    class_name = serializers.CharField()
    field_name = serializers.CharField()  # type: ignore[assignment] # we're not using serializer in the sense of a field; safe to override
    pk = serializers.CharField(required=False)
    pks = serializers.ListField(child=serializers.CharField(), required=False)
    exclude_empty = serializers.BooleanField(required=False)

    def __init__(self, registry, **kwargs):
        self.registry = registry
        super().__init__(**kwargs)

    def validate(self, attrs):
        if attrs["class_name"] not in self.registry.server_choices_registry:
            raise ValidationError({"class_name": "Unknown class_name"})
        if attrs["field_name"] not in self.registry.server_choices_registry[attrs["class_name"]].fields:
            raise ValidationError({"field_name": "Unknown field_name"})
        return attrs


class ServerChoicesFilterSet(FilterSet):
    exclude_empty = BooleanFilter()


class ServerChoicesView(APIView):
    """View to handle serving all registered server choices

    See :meth:`~alliance_platform.server_choices.server_choices` for documentation on how choices are registered.

    Permission checks are done based on the ``perm`` argument on the registration.

    This view should be added to ``urlpatterns`` and will then be used for any server choices:

    .. code-block:: python

        path("api/server-choices/", ServerChoicesView.as_view())

    Server choices can optionally use a custom registry. If this is used then a view needs to be registered for each
    registry.

    .. code-block:: python

        urlpatterns += [
            # Handles the default registry
            path("api/server-choices/", ServerChoicesView.as_view()),
            # Handles a custom registry called CustomChoicesRegistry
            path("api/server-choices/", ServerChoicesView.as_view({"registry": CustomChoicesRegistry })),
        ]


    When the view is called it expects ``class_name`` and ``field_name`` query params. These are used to lookup the registration.
    Optionally ``pk`` or ``pks`` can also be passed to retrieve the values for the specified key or keys (eg. when initially
    rendering an existing field that has a value you need the associated label).

    The return value is serialized according to :meth:`~alliance_platform.server_choices.register.ServerChoiceFieldRegistration.serialize`
    """

    registry = default_server_choices_registry

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        registry = cast(APIViewProtocol, view).initkwargs.get("registry", default_server_choices_registry)
        if registry.attached_view:
            import warnings

            warnings.warn(
                f"{registry} has already been attached to one ServerChoicesView. Pass a different registry in like `ServerChoicesView.as_view({{ registry: another_reg }})`"
            )
        registry.attached_view = view
        return view

    def get(self, request):
        input_serializer = ServerChoicesInputSerializer(
            registry=self.registry,
            data=(
                underscoreize(request.query_params)
                | ({"pks": request.query_params.getlist("pks")} if "pks" in request.query_params else {})
            ),
        )
        input_serializer.is_valid(raise_exception=True)
        pk = input_serializer.data.get("pk", None)
        pks = input_serializer.validated_data.get("pks", None)
        field_reg = self.registry.server_choices_registry[input_serializer.data["class_name"]].fields[
            input_serializer.data["field_name"]
        ]

        if not field_reg.has_perm(request):
            raise PermissionDenied

        if pk is not None:
            try:
                record = field_reg.get_record(pk, request)
            except ObjectDoesNotExist:
                raise NotFound
            return Response(field_reg.serialize(record, request))
        if pks is not None:
            records = field_reg.get_records(pks, request)
            serialized_records = field_reg.serialize(records, request)
            by_id = {str(r[field_reg.value_field]): r for r in serialized_records}
            return Response([by_id[pk] for pk in map(str, pks) if pk in by_id])

        choices = field_reg.filter_choices(field_reg.get_choices(request), request)

        def serialize_with_empty_label(choices, force_no_empty=False):
            data = field_reg.serialize(choices, request)
            if (
                not force_no_empty
                and field_reg.empty_label
                and not input_serializer.data.get("exclude_empty")
            ):
                if isinstance(data, MutableSequence):
                    data.insert(0, {field_reg.value_field: "", field_reg.label_field: field_reg.empty_label})
                else:
                    raise ValueError(
                        f"serialize_with_empty_label() got {data} but is expecting a list; is the `choices` passed to it singular?"
                    )
            return data

        if field_reg.pagination_class:
            paginator = field_reg.pagination_class()
            page = paginator.paginate_queryset(choices, request, view=self)
            if page is not None:
                return paginator.get_paginated_response(
                    serialize_with_empty_label(page, paginator.page.has_previous())
                )
        return Response(serialize_with_empty_label(choices))
