from collections.abc import MutableSequence
from typing import Any
from typing import Protocol

from allianceutils.util import underscoreize
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.core.paginator import InvalidPage
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.generic import View

from .field_registry import default_server_choices_registry
from .pagination import SimplePaginator


class APIViewProtocol(Protocol):
    initkwargs: dict[str, Any]  # drf-stubs is missing this


def generate_serialized_server_choices_input(registry, data: dict[str, Any]):
    if "class_name" not in data:
        raise ValidationError({"class_name": "class_name is required"})
    elif data["class_name"] not in registry.server_choices_registry:
        raise ValidationError({"class_name": "Unknown class_name"})

    if "field_name" not in data:
        raise ValidationError({"field_name": "field_name is required"})
    elif data["field_name"] not in registry.server_choices_registry[data["class_name"]].fields:
        raise ValidationError({"field_name": "Unknown field_name"})

    return {
        "class_name": data["class_name"],
        "field_name": data["field_name"],
        "pk": data.get("pk"),
        "pks": data.get("pks"),
        "exclude_empty": data.get("exclude_empty"),
    }


class ServerChoicesView(View):
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
    def as_view(cls, **kwargs):
        view = super().as_view(**kwargs)
        registry = kwargs.get("registry", default_server_choices_registry)
        if registry.attached_view:
            import warnings

            warnings.warn(
                f"{registry} has already been attached to one ServerChoicesView. Pass a different registry in like `ServerChoicesView.as_view({{ registry: another_reg }})`"
            )
        registry.attached_view = view
        return view

    def get(self, request):
        try:
            serialized_input = generate_serialized_server_choices_input(
                registry=self.registry,
                data=(
                    underscoreize(request.GET)
                    | ({"pks": request.GET.getlist("pks")} if "pks" in request.GET else {})
                ),
            )
        except ValidationError:
            return HttpResponse(ValidationError.error_dict, status=400)
        pk = serialized_input.get("pk", None)
        pks = serialized_input.get("pks", None)
        field_reg = self.registry.server_choices_registry[serialized_input["class_name"]].fields[
            serialized_input["field_name"]
        ]

        if not field_reg.has_perm(request):
            return HttpResponse("You do not have permission to perform this action", status=403)

        if pk is not None:
            try:
                record = field_reg.get_record(pk, request)
            except ObjectDoesNotExist:
                return HttpResponse("Not found", status=404)
            return JsonResponse(field_reg.serialize(record, request), safe=False)
        if pks is not None:
            records = field_reg.get_records(pks, request)
            serialized_records = field_reg.serialize(records, request)
            by_id = {str(r[field_reg.value_field]): r for r in serialized_records}
            return JsonResponse([by_id[pk] for pk in map(str, pks) if pk in by_id], safe=False)

        choices = field_reg.filter_choices(field_reg.get_choices(request), request)

        def serialize_with_empty_label(choices, force_no_empty=False):
            data = field_reg.serialize(choices, request)
            if not force_no_empty and field_reg.empty_label and not serialized_input.get("exclude_empty"):
                if isinstance(data, MutableSequence):
                    data.insert(
                        0,
                        {
                            field_reg.value_field: "",
                            field_reg.label_field: field_reg.empty_label,
                        },
                    )
                else:
                    raise ValueError(
                        f"serialize_with_empty_label() got {data} but is expecting a list; is the `choices` passed to it singular?"
                    )
            return data

        if field_reg.page_size != 0:
            paginator = SimplePaginator(field_reg.page_size)
            try:
                page = paginator.paginate_queryset(choices, request, view=self)
            except InvalidPage:
                return HttpResponse("Invalid page", status=404)

            if page is not None:
                return paginator.get_paginated_response(serialize_with_empty_label(page, page.has_previous()))
        return JsonResponse(serialize_with_empty_label(choices), safe=False)
