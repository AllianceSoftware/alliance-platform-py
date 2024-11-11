from __future__ import annotations

from hashlib import shake_256
from typing import TYPE_CHECKING
from typing import Callable

from alliance_platform.storage.async_uploads.storage.base import AsyncUploadStorage
from django.db.models import Field
from django.http import HttpResponse

if TYPE_CHECKING:
    # circular imports
    from alliance_platform.storage.async_uploads.models import AsyncFileField
    from alliance_platform.storage.async_uploads.models import AsyncImageField


def is_same_field(field1: Field, field2: Field) -> bool:
    """Are two fields the same?

    This doesn't just do equality check as in some cases (eg. test runner) the
    same model appears to be loaded twice
    """
    return field1.model._meta.label == field2.model._meta.label and field1.name == field2.name


class AsyncFieldRegistry:
    """A registry for async fields. This allows looking up a field by its ID.

    In most cases the default registry :code:`default_async_field_registry` is suitable and more than one
    registry is not necessary.
    """

    # This is for easy lookup using the unique name for a class. The name is what
    # can be passed from the frontend to identify a particular registration
    fields_by_id: dict[str, AsyncFileField | AsyncImageField]
    # The attached GenerateUploadUrlView as returned by GenerateUploadUrlView.as_view(). This is attached automatically
    # when GenerateUploadUrlView.as_view() is called.
    attached_view: Callable[..., HttpResponse] | None = None

    # The attached AsyncFileDownloadView as returned by AsyncFileDownloadView.as_view(). This is attached automatically
    # when AsyncFileDownloadView.as_view() is called.
    attached_download_view: Callable[..., HttpResponse] | None = None

    def __init__(self, name):
        """
        Args:
            name: A name for this registration. This is just used to make debugging easier when printing out registration instances.
        """
        self.name = name
        self.fields_by_id = {}

    def __str__(self):
        return f"AsyncFieldRegistry(name='{self.name}')"

    def generate_id(self, field: Field):
        """Generate a string ID for a field to be used to lookup into ``fields_by_id``.

        This is passed from the frontend to uniquely identify a field in a registry.
        """
        # Don't expose label to the frontend
        label = shake_256(field.model._meta.label.encode()).hexdigest(8)
        field_name = shake_256(field.name.encode()).hexdigest(8)
        # Include field name to make debugging a bit easier and avoid collisions. This isn't
        # exposing anything we care about as this ID is always associated with the named field
        # on the frontend anyway
        return f"{label}.{field_name}.{field.name}"

    def register_field(self, field: AsyncFileField | AsyncImageField):
        """Register a field in this registry."""
        if not isinstance(getattr(field, "storage", None), AsyncUploadStorage):
            raise ValueError(
                f"Only fields that implement AsyncUploadStorage are supported. {field} does not implement AsyncUploadStorage."
            )
        field_id = self.generate_id(field)
        if field_id in self.fields_by_id:
            if not is_same_field(self.fields_by_id[field_id], field):
                raise ValueError(
                    f"Collision on field id '{field_id}' for field {field} vs {self.fields_by_id[field_id]}"
                )
        else:
            # don't want to register fake migration models
            if field.model.__module__ == "__fake__":
                return

            self.fields_by_id[field_id] = field

    def get_url_patterns(self):
        """Get the required URL patterns for the storage classes used by the registered fields

        This calls :meth:`~alliance_platform.storage.async_uploads.base.AsyncUploadStorage.get_url_patterns` on each
        storage instance and combines the results.

        Usage::

            from django.urls import path
            from django.urls import include
            from alliance_platform.storage.async_uploads.registry import default_async_field_registry

            urlpatterns = [path("async-uploads/", include(default_async_field_registry.get_url_patterns()))]
        """
        storage_instances = {field.storage for field in self.fields_by_id.values()}

        patterns = []
        for storage in storage_instances:
            patterns += storage.get_url_patterns(self)
        return patterns


#: The default registry class to use when none is provided.
default_async_field_registry = AsyncFieldRegistry("default")
