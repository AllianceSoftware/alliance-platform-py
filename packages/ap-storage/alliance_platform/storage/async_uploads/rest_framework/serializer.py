from typing import cast

from alliance_platform.storage.async_uploads.forms import AsyncFileInputDataLengthValidator
from alliance_platform.storage.async_uploads.forms import AsyncFileInputDataValidator
from alliance_platform.storage.async_uploads.models import AsyncFieldFile
from alliance_platform.storage.async_uploads.models import AsyncFileField as AsyncFileBaseField
from alliance_platform.storage.async_uploads.models import AsyncFileInputData
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError as CoreValidationError

try:
    from rest_framework import serializers
    from rest_framework.fields import empty
    from rest_framework.fields import get_attribute
    from rest_framework.utils.formatting import lazy_format
except ImportError as e:
    raise ImproperlyConfigured(
        "Optional dependency 'rest_framework' is not installed. This is required to make use of the DRF fields."
    ) from e


class AsyncFileField(serializers.ModelField):
    """Field that works with :class:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage` to handle uploading directly to
    external service like S3 or Azure.

    Unlike most fields this field must be backed by an underlying model field specified in the ``model_field``
    kwarg. This is inferred automatically if using a base ModelSerializer class with the following:

    .. code:: python

        import alliance_platform.storage.async_uploads.models as async_file_fields
        class BaseModelSerializer(ModelSerializer):
            serializer_field_mapping = {
                **ModelSerializer.serializer_field_mapping,
                async_file_fields.AsyncFileField: AsyncFileField,
                async_file_fields.AsyncImageField: AsyncImageField,
            }

    This field expects to receive data in the shape { "key": "/storage/file.png", "name": "file.png" }. It will
    extract the key to be set on the file field. See :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin`
    for more details. For :class:`~alliance_platform.storage.async_uploads.rest_framework.AsyncImageField` the ``width`` and ``height``
    keys may also exist in the data. See :class:`~alliance_platform.async_uploads.models.AsyncFileInputData`

    Serialized data is in shape  { "key": "/storage/file.png", "name": "file.png", "url": "/download/?field_id=..." }
    which is supported by the UploadWidget on the frontend.
    """

    default_error_messages = {
        "max_length": "Ensure this filename has at most {max_length} characters.",
        "invalid_key": "{error}",
    }

    def __init__(self, *args, **kwargs):
        max_length = kwargs.pop("max_length", None)
        # ModelField handles max_length if provided - bypass this so we can use custom validator
        super().__init__(*args, **kwargs)
        self.max_length = max_length
        if self.max_length is not None:
            format_str = cast(str, self.error_messages["max_length"])
            message = lazy_format(format_str, max_length=self.max_length)
            self.validators.append(
                AsyncFileInputDataLengthValidator(int(self.max_length), message=cast(str, message))
            )
        self.validators.append(AsyncFileInputDataValidator())

    def get_value(self, dictionary):
        """Convert incoming value into AsyncFileInputData"""
        value = super().get_value(dictionary)
        if not value or value == empty:
            return value
        if not isinstance(value, dict):
            return value

        parent_meta = self.parent.Meta
        pk_name = parent_meta.model._meta.pk.name
        if pk_name in dictionary:
            self._instance_pk = dictionary[pk_name]

        return AsyncFileInputData.create_from_user_input(value)

    def to_internal_value(self, value: AsyncFileInputData):
        if isinstance(value, AsyncFileInputData):
            value.update_dimension_cache(self.model_field)
            existing_value = (
                None if not self.parent.instance else getattr(self.parent.instance, self.model_field.name)
            )

            if not existing_value and (nested_pk := getattr(self, "_instance_pk", None)):
                parent_meta = self.parent.Meta  # type: ignore[attr-defined] # metaclass
                instance = parent_meta.model._base_manager.get(pk=nested_pk)
                existing_value = getattr(instance, self.model_field.name)

            try:
                value.validate_key(
                    cast(AsyncFileBaseField, self.model_field),
                    cast(str | AsyncFieldFile | None, existing_value),
                )
            except CoreValidationError as e:
                self.fail("invalid_key", error=e)
        return value

    def to_representation(self, value):
        if self.source_attrs:
            # if source is set to e.g. fk1.fk2.file_field, we need to that final relation 'fk2'
            # in the chain (but not the field - that's handled by value_from_object below)
            value = get_attribute(value, self.source_attrs[:-1])
        value = self.model_field.value_from_object(value)
        if not value:
            return None
        try:
            url = value.url
        except Exception:
            # url isn't critical; if it fails ignore it and frontend may just not be able
            # to show a thumbnail
            url = None
        return {"key": value.name, "name": value.name.split("/")[-1], "url": url}


class AsyncImageField(AsyncFileField):
    """Same behaviour as :class:`~alliance_platform.storage.async_uploads.rest_framework.AsyncFileField`

    This exists as a separate class to allow codegen to differentiate for the purpose
    of customising the field & widget on the frontend."""

    pass
