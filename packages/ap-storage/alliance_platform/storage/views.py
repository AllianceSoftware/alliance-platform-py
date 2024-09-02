from typing import Any
from typing import Protocol
from typing import cast

from alliance_platform.storage.models import AsyncTempFile
from alliance_platform.storage.registry import AsyncFieldRegistry
from alliance_platform.storage.registry import default_async_field_registry
from django.core.exceptions import BadRequest
from django.db import models
from django.db.models import Manager
from django.http import HttpResponseRedirect
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class GenerateUploadUrlViewInputSerializer(serializers.Serializer):
    field_id = serializers.CharField()
    filename = serializers.CharField()
    params = serializers.JSONField(required=False)
    instance_id = serializers.CharField(required=False)

    def __init__(self, registry: AsyncFieldRegistry, **kwargs):
        self.registry = registry
        super().__init__(**kwargs)

    def validate(self, attrs):
        if attrs["field_id"] not in self.registry.fields_by_id:
            raise ValidationError({"field_id": "Unknown field_id"})
        return attrs


class APIViewProtocol(Protocol):
    initkwargs: dict[str, Any]  # drf-stubs is missing this


class ViewsetProtocol(Protocol):
    initkwargs: dict[str, Any]  # drf-stubs is missing this too..


class ModelWithDefaultManager(Protocol):
    objects: Manager


class GenerateUploadUrlView(APIView):
    """View to generate a URL using :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.generate_upload_url`.

    Each view is tied to a specific registry which you can specify in the ``registry`` kwarg (defaults to :data:`~alliance_platform.storage.registry.default_async_field_registry`).

    This view expects a ``async_field_id``, a ``filename`` and optionally an ``instance_id`` if it's an update for an existing
    record. ``async_field_id`` is used to look up in ``registry`` the matching ``field`` instance. From the retrieved field
    instance the corresponding :class:`~alliance_platform.storage.storage.AsyncUploadStorage` is retrieved along with the permissions
    to check (see :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin` for where to specify this).

    If the permission check passes a :class:`~alliance_platform.storage.models.AsyncTempFile` record is created which stores the
    ``filename`` and a generated key that will be used as a temporary location to upload the file to. An upload URL
    returned from :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.generate_upload_url` and the temporary key is returned
    to the frontend. The frontend will submit the returned temporary key from the form and save it on the target model.
    On save the file is then moved to the permanent location using :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.move_file`
    (this happens as part of :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin`)

    See :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin` for a detailed explanation of how all the pieces fit together.
    """

    registry = default_async_field_registry

    @classmethod
    def as_view(cls, **initkwargs):
        view: APIViewProtocol = cast(APIViewProtocol, super().as_view(**initkwargs))
        registry = view.initkwargs.get("registry", default_async_field_registry)
        if registry.attached_view:
            import warnings

            warnings.warn(
                f"{registry} has already been attached to one GenerateUploadUrlView. Pass a different registry in like `GenerateUploadUrlView.as_view({{ registry: another_reg }})`"
            )
        registry.attached_view = view
        return view

    def get(self, request: Request) -> Response:
        input_serializer = GenerateUploadUrlViewInputSerializer(
            registry=self.registry, data=request.query_params
        )
        input_serializer.is_valid(raise_exception=True)
        field_id = input_serializer.data["field_id"]
        field = self.registry.fields_by_id[field_id]
        instance_id = input_serializer.data.get("instance_id")
        obj = None
        if instance_id:
            manager = cast(ModelWithDefaultManager, field.model).objects
            obj = manager.get(pk=instance_id)
        if not request.user.has_perm(field.perm_update if obj else field.perm_create, obj):
            raise PermissionDenied

        filename = input_serializer.data["filename"]
        if field.file_restrictions:
            if not field.is_valid_filetype(filename):
                raise BadRequest

        temp_file = AsyncTempFile.create_for_field(field, filename)
        conditions = []
        if field.max_size:
            conditions.append(["content-length-range", 0, field.max_size * 1024 * 1024])
        # this matches any, but is OK because we are signing a single key only anyway which will restrict the type
        conditions.append(["starts-with", "$Content-Type", ""])
        return Response(
            {
                "uploadUrl": field.storage.generate_upload_url(
                    temp_file.key, fields=input_serializer.data.get("params"), conditions=conditions or None
                ),
                "key": temp_file.key,
            }
        )


class AsyncFileDownloadViewSerializer(serializers.Serializer):
    field_id = serializers.CharField()
    instance_id = serializers.CharField(required=False)

    def __init__(self, registry: AsyncFieldRegistry, **kwargs):
        self.registry = registry
        super().__init__(**kwargs)

    def validate(self, attrs):
        if attrs["field_id"] not in self.registry.fields_by_id:
            raise ValidationError({"field_id": "Unknown field_id"})
        return attrs


class DownloadRedirectView(APIView):
    """View that checks permissions and redirects to a download URL using :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.generate_download_url`.

    Each view is tied to a specific registry which you can specify in the ``registry`` kwarg (defaults to :data:`~alliance_platform.storage.registry.default_async_field_registry`).

    This view expects a ``async_field_id`` and ``instance_id`` which is the primary key of the record the file field is
    attached to. record. ``async_field_id`` is used to look up in ``registry`` the matching ``field`` instance. From the
    retrieved field instance the corresponding :class:`~alliance_platform.storage.storage.AsyncUploadStorage` is retrieved along
    with the permission (``perm_download``) to check (see :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin` for
    where to specify this).

    Once the permission check has passed the view will redirect to the URL returned from
    :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.generate_download_url`.

    See :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin` for a detailed explanation of how all the pieces fit together.
    """

    registry = default_async_field_registry

    @classmethod
    def as_view(cls, **initkwargs):
        view: APIViewProtocol = cast(APIViewProtocol, super().as_view(**initkwargs))
        registry = view.initkwargs.get("registry", default_async_field_registry)
        if registry.attached_download_view:
            import warnings

            warnings.warn(
                f"{registry} has already been attached to one AsyncFileDownloadView. Pass a different registry in like `AsyncFileDownloadView.as_view({{ registry: another_reg }})`"
            )
        registry.attached_download_view = view
        return view

    def get(self, request):
        input_serializer = AsyncFileDownloadViewSerializer(registry=self.registry, data=request.query_params)
        input_serializer.is_valid(raise_exception=True)
        field_id = input_serializer.data["field_id"]
        field = self.registry.fields_by_id[field_id]
        instance_id = input_serializer.data.get("instance_id")

        manager = cast(ModelWithDefaultManager, field.model).objects
        obj: models.Model = get_object_or_404(manager, pk=instance_id)
        if not request.user.has_perm(field.perm_detail, obj):
            raise PermissionDenied
        value = getattr(obj, field.name)
        return HttpResponseRedirect(field.storage.generate_download_url(value.name))
