from typing import cast

from alliance_platform.storage.async_uploads.forms import AsyncFileField as AsyncFileFormField
from alliance_platform.storage.async_uploads.forms import AsyncImageField as AsyncImageFormField
from alliance_platform.storage.async_uploads.models.models import AsyncFieldFile
from alliance_platform.storage.async_uploads.models.models import AsyncFileInputData
from alliance_platform.storage.async_uploads.models.models import AsyncFileMixin
from alliance_platform.storage.async_uploads.models.models import FieldFileMixin
from django.db.models import FileField
from django.db.models import ImageField
from django.db.models.fields.files import FileDescriptor
from django.db.models.fields.files import ImageFieldFile


class AsyncFileDescriptor(FileDescriptor):
    """Extracts the ``key`` from AsyncFileInputData to be set against instance"""

    def __set__(self, instance, value):
        if isinstance(value, AsyncFileInputData):
            value.validate_key(cast(AsyncFileField, self.field), instance.__dict__.get(self.field.name))
            value = value.key
        super().__set__(instance, value)


class AsyncFileField(AsyncFileMixin, FileField):  # type: ignore[misc] # mypy dont like the fact that we're using AsyncUploadStorage and report it as conflict w/ FileField
    """A FileField that works with AsyncUploadStorage to directly upload somewhere (eg. S3) from the frontend

    See :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin` for more details on how this field works.
    """

    attr_class = AsyncFieldFile
    descriptor_class = AsyncFileDescriptor

    def formfield(self, **kwargs):
        return super().formfield(
            **{
                "form_class": AsyncFileFormField,
                "async_field_id": self.async_field_registry.generate_id(self),
                "async_field_registry": self.async_field_registry,
                "storage": self.storage,
                **kwargs,
            }
        )


class AsyncImageDescriptor(FileDescriptor):
    """Extracts the ``key`` from AsyncFileInputData to be set against instance & handles width/height

    If width & height are present they are set on the field and handled by
    :meth:`alliance_platform.storage.async_uploads.models.AsyncImageField.update_dimension_fields`.
    """

    def __set__(self, instance, value):
        if isinstance(value, AsyncFileInputData):
            value.validate_key(cast(AsyncFileField, self.field), instance.__dict__.get(self.field.name))
            value.update_dimension_cache(self.field)
            value = value.key
            super().__set__(instance, value)
        else:
            # From ImageFileDescriptor:
            # To prevent recalculating image dimensions when we are instantiating
            # an object from the database (bug #11084), only update dimensions if
            # the field had a value before this assignment.  Since the default
            # value for FileField subclasses is an instance of field.attr_class,
            # previous_file will only be None when we are called from
            # Model.__init__().  The ImageField.update_dimension_fields method
            # hooked up to the post_init signal handles the Model.__init__() cases.
            # Assignment happening outside of Model.__init__() will trigger the
            # update right here.

            # We only do this if we don't have an AsyncFileInputData as
            # that contains the width / height submitted from the
            # frontend and so avoids potentially downloading the file
            # to get the width/height.
            previous_file = instance.__dict__.get(self.field.name)
            super().__set__(instance, value)
            # Don't compare value != previous_file as it doesn't guarantee the underlying
            # file hasn't changed (eg. the key could be set to same filename again after
            # a new upload but be a different file)
            if previous_file is not None:
                cast(AsyncImageField, self.field).update_dimension_fields(instance, force=True)


class AsyncImageFieldFile(FieldFileMixin, ImageFieldFile):
    pass


class AsyncImageField(AsyncFileMixin, ImageField):  # type: ignore[misc] # mypy dont like the fact that we're using AsyncUploadStorage and report it as conflict w/ FileField
    """A ImageField that works with AsyncUploadStorage to directly upload somewhere (eg. S3) from the frontend

    This supports ``width_field`` and ``height_field`` in two ways

    1) (preferred) The frontend passes the width & height with the form submission. This is supported with the
    :class:`~alliance_platform.storage.async_uploads.forms.AsyncImageField` form field (the default). This works in
    conjunction with the ``UploadWidget`` on the frontend.

    2) (slow) Same behaviour as :class:`~django.db.models.ImageField` which requires the file to be downloaded
    and processed with Pillow.

    See :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin` for more details on how this field works.
    """

    descriptor_class = AsyncImageDescriptor
    attr_class = AsyncImageFieldFile

    # Cache dimensions as (width, height) from AsyncImageDescriptor. Used in update_dimension_fields
    dimension_cache: tuple[int, int] | None

    # Don't check if Pillow is installed. This is used to get dimensions of images.
    _supress_pillow_check: bool

    width_field: str | None
    height_field: str | None

    def __init__(self, *args, suppress_pillow_check=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._suppress_pillow_check = suppress_pillow_check
        self.dimension_cache = None

    def check(self, **kwargs):
        if self._suppress_pillow_check:
            return super(ImageField, self).check(**kwargs)
        return super().check(**kwargs)

    def update_dimension_fields(self, instance, force=False, *args, **kwargs):
        # If we have a cache use that otherwise fall back to default. Note that
        # the default will open the file to work out dimensions and so with
        # remote backends like S3 would result in downloading the file first.
        if self.dimension_cache:
            has_dimension_fields = self.width_field or self.height_field
            if not has_dimension_fields or self.attname not in instance.__dict__:
                return
            width, height = self.dimension_cache
            self.dimension_cache = None
            if self.width_field:
                setattr(instance, self.width_field, width)
            if self.height_field:
                setattr(instance, self.height_field, height)
        else:
            super().update_dimension_fields(instance, force, *args, **kwargs)

    def before_move_file(self, instance):
        """Prior to moving file populate the dimensions cache

        This is so the moved file retains same dimensions as prior to move without
        needing to recalculate it (ie. it's the same file, just in a different location).
        """
        has_dimension_fields = self.width_field and self.height_field
        if has_dimension_fields and not self.dimension_cache:
            width = getattr(
                instance, cast(str, self.width_field)
            )  # here -> has_dimension_fields -> str | None is str
            height = getattr(instance, cast(str, self.height_field))
            self.dimension_cache = (width, height)

    def formfield(self, **kwargs):
        return super().formfield(
            **{
                "form_class": AsyncImageFormField,
                "async_field_id": self.async_field_registry.generate_id(self),
                "async_field_registry": self.async_field_registry,
                "storage": self.storage,
                **kwargs,
            }
        )
