import json
from json import JSONDecodeError
from typing import Any
from typing import Protocol
from typing import cast

from alliance_platform.storage.async_uploads.models import AsyncTempFile
from alliance_platform.storage.async_uploads.registry import AsyncFieldRegistry
from alliance_platform.storage.async_uploads.registry import default_async_field_registry
from allianceutils.util import camelize
from allianceutils.util import underscoreize
from django.core.exceptions import BadRequest
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Manager
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseNotFound
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from django.views import View


def validate_generate_upload_url(data: QueryDict, registry: AsyncFieldRegistry):
    field_id = data.get("field_id")
    filename = data.get("filename")
    params = data.get("params", None)
    instance_id = data.get("instance_id", None)
    errors: dict[str, str] = {}

    if not field_id:
        errors["field_id"] = "This field is required."
    elif field_id not in registry.fields_by_id:
        errors["field_id"] = "Unknown fieldId"
    if not filename:
        errors["filename"] = "This field is required."
    if errors:
        raise ValidationError(errors)
    if params:
        try:
            params = json.loads(params)
        except JSONDecodeError:
            errors["params"] = "Invalid JSON"

    return {
        "field_id": field_id,
        "filename": filename,
        "params": params,
        "instance_id": instance_id,
    }


class ViewProtocol(Protocol):
    view_initkwargs: dict[str, Any]  # django-stubs is missing this


class ModelWithDefaultManager(Protocol):
    objects: Manager


class GenerateUploadUrlView(View):
    """View to generate a URL using :meth:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage.generate_upload_url`.

    Each view is tied to a specific registry which you can specify in the ``registry`` kwarg (defaults to :data:`~alliance_platform.storage.async_uploads.registry.default_async_field_registry`).

    This view expects a ``async_field_id``, a ``filename`` and optionally an ``instance_id`` if it's an update for an existing
    record. ``async_field_id`` is used to look up in ``registry`` the matching ``field`` instance. From the retrieved field
    instance the corresponding :class:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage` is retrieved along with the permissions
    to check (see :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin` for where to specify this).

    If the permission check passes a :class:`~alliance_platform.storage.async_uploads.models.AsyncTempFile` record is created which stores the
    ``filename`` and a generated key that will be used as a temporary location to upload the file to. An upload URL
    returned from :meth:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage.generate_upload_url` and the temporary key is returned
    to the frontend. The frontend will submit the returned temporary key from the form and save it on the target model.
    On save the file is then moved to the permanent location using :meth:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage.move_file`
    (this happens as part of :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin`)

    See :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin` for a detailed explanation of how all the pieces fit together.

    This view is automatically registered if you have followed the :ref:`register-urls` guide.
    """

    registry = default_async_field_registry

    @classmethod
    def as_view(cls, **initkwargs: Any):
        view: ViewProtocol = cast(ViewProtocol, super().as_view(**initkwargs))
        registry = view.view_initkwargs.get("registry", default_async_field_registry)
        if registry.attached_view:
            import warnings

            warnings.warn(
                f"{registry} has already been attached to one GenerateUploadUrlView. Pass a different registry in like `GenerateUploadUrlView.as_view({{ registry: another_reg }})`"
            )
        registry.attached_view = view
        return view

    def get(self, request: HttpRequest) -> HttpResponse:
        try:
            validated_data = validate_generate_upload_url(underscoreize(request.GET), self.registry)
        except ValidationError as e:
            return JsonResponse(camelize(e.message_dict), status=400)
        field_id = validated_data["field_id"]
        field = self.registry.fields_by_id[field_id]
        instance_id = validated_data["instance_id"]
        obj = None
        if instance_id:
            manager = cast(ModelWithDefaultManager, field.model).objects
            obj = manager.get(pk=instance_id)
        required_perm = field.perm_update if obj else field.perm_create
        if required_perm is not None and not request.user.has_perm(required_perm, obj):
            raise PermissionDenied

        filename = validated_data["filename"]
        if field.file_restrictions:
            if not field.is_valid_filetype(filename):
                raise BadRequest

        temp_file = AsyncTempFile.create_for_field(field, filename)
        conditions = []
        if field.max_size:
            conditions.append(["content-length-range", 0, field.max_size * 1024 * 1024])
        # this matches any, but is OK because we are signing a single key only anyway which will restrict the type
        conditions.append(["starts-with", "$Content-Type", ""])
        return JsonResponse(
            {
                "uploadUrl": field.storage.generate_upload_url(
                    temp_file.key,
                    field_id,
                    fields=validated_data.get("params"),
                    conditions=conditions or None,
                ),
                "key": temp_file.key,
            }
        )


def validate_async_file_download(data: QueryDict, registry: AsyncFieldRegistry):
    field_id = data.get("field_id")
    instance_id = data.get("instance_id", None)

    if not field_id:
        raise ValidationError({"field_id": "This field is required."})

    if field_id not in registry.fields_by_id:
        raise ValidationError({"field_id": "Unknown fieldId"})

    return {"field_id": field_id, "instance_id": instance_id}


class DownloadRedirectView(View):
    """View that checks permissions and redirects to a download URL using :meth:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage.generate_download_url`.

    Each view is tied to a specific registry which you can specify in the ``registry`` kwarg (defaults to :data:`~alliance_platform.storage.async_uploads.registry.default_async_field_registry`).

    This view expects a ``async_field_id`` and ``instance_id`` which is the primary key of the record the file field is
    attached to. record. ``async_field_id`` is used to look up in ``registry`` the matching ``field`` instance. From the
    retrieved field instance the corresponding :class:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage` is retrieved along
    with the permission (``perm_download``) to check (see :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin` for
    where to specify this).

    Once the permission check has passed the view will redirect to the URL returned from
    :meth:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage.generate_download_url`.

    See :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin` for a detailed explanation of how all the pieces fit together.

    This view is automatically registered if you have followed the :ref:`register-urls` guide.
    """

    registry = default_async_field_registry

    @classmethod
    def as_view(cls, **initkwargs: Any):
        view: ViewProtocol = cast(ViewProtocol, super().as_view(**initkwargs))
        registry = view.view_initkwargs.get("registry", default_async_field_registry)
        if registry.attached_download_view:
            import warnings

            warnings.warn(
                f"{registry} has already been attached to one AsyncFileDownloadView. Pass a different registry in like `AsyncFileDownloadView.as_view({{ registry: another_reg }})`"
            )
        registry.attached_download_view = view
        return view

    def get(self, request: HttpRequest):
        try:
            validated_data = validate_async_file_download(underscoreize(request.GET), self.registry)
        except ValidationError as e:
            return JsonResponse(camelize(e.message_dict), status=400)
        field_id = validated_data["field_id"]
        field = self.registry.fields_by_id[field_id]
        instance_id = validated_data.get("instance_id")

        manager = cast(ModelWithDefaultManager, field.model).objects
        obj: models.Model = get_object_or_404(manager, pk=instance_id)
        if field.perm_detail is not None and not request.user.has_perm(field.perm_detail, obj):
            raise PermissionDenied
        value = getattr(obj, field.name)
        if not value:
            return HttpResponseNotFound(f"No value set for {field.name}")
        return HttpResponseRedirect(
            field.storage.generate_download_url(value.name, field_id, **field.download_params)
        )
