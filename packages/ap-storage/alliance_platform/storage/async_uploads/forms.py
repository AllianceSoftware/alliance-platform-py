import json
from json import JSONDecodeError

from alliance_platform.storage.async_uploads.models import AsyncFileInputData
from alliance_platform.storage.async_uploads.models import AsyncTempFile
from alliance_platform.storage.async_uploads.registry import AsyncFieldRegistry
from alliance_platform.storage.async_uploads.storage.base import AsyncUploadStorage
from django import forms
from django.core import validators
from django.core.exceptions import ValidationError
from django.forms.widgets import Input
from django.urls import reverse
from django.utils.deconstruct import deconstructible


# This does not extend FileInput as we don't actually receive a file
# from the frontend. Instead we get a string which represents the key
# for the storage backend.
class AsyncFileInput(Input):
    """Input for handling async uploads

    This handles the submission value from UploadWidget and converts it to an instance
    of :class:`~alliance_platform.storage.async_uploads.models.AsyncFileInputData`. This is then handled
    on the descriptor classes for :class:`~alliance_platform.storage.async_uploads.models.AsyncFileField`
    and :class:`~alliance_platform.storage.async_uploads.models.AsyncImageField`.

    To customise the widget rendered on the frontend you can override the template
    ``alliance_platform/storage/widgets/async_file_input.html``.
    """

    input_type = "async-file"
    template_name = "alliance_platform/storage/widgets/async_file_input.html"

    # This is needed to generate URL to file in case where we only
    # have the AsyncTempFile (see `format_value`)
    storage: AsyncUploadStorage

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)

        # Resolving the upload url needs to be delayed until render so that the
        # GenerateUploadUrl view has a chance to attach to the registry. Resolve
        # that here.
        async_field_registry = context["widget"]["attrs"].pop("async_field_registry", None)
        if not async_field_registry:
            raise ValueError("AsyncFileInput expects a 'async_field_registry' to be passed in widget attrs")

        context["widget"]["attrs"]["generate_upload_url"] = reverse(async_field_registry.attached_view)

        return context

    def format_value(self, value):
        """Given a value return it in serialized format expected by frontend

        Frontend expects a json string like:

            {"key": "/some/storage/location/test.png", "name": "test.png" }
        """
        if not value:
            return None
        if isinstance(value, AsyncFileInputData):
            # If a submission occurs but isn't successful (eg. validation fails on another
            # field) we end up with a string which should match the key on AsyncTempFile
            try:
                temp_file = AsyncTempFile.objects.get(key=value.key)
                return json.dumps(
                    {
                        "key": temp_file.key,
                        "name": temp_file.original_filename,
                        "url": self.storage.url(temp_file.key),
                    }
                )
            except AsyncTempFile.DoesNotExist:
                return json.dumps(
                    {
                        "key": value.key,
                        "name": value.name,
                    }
                )
        try:
            url = value.url
        except Exception:
            # url isn't critical; if it fails ignore it and frontend may just not be able
            # to show a thumbnail
            url = None
        return json.dumps({"key": value.name, "name": value.name.split("/")[-1], "url": url})

    def value_from_datadict(self, data, files, name):
        """This expects to receive a valid json string that can be used to instantiate AsyncFileInputData

        If invalid JSON is received this is handled by the ``AsyncFileInputDataValidator`` which will
        raise a ValidationError. We load the json here rather than in the field ``clean`` so that we have
        the ``AsyncFileInputData`` in ``format`` for the case where there's a ValidationError and form
        re-renders.

        AsyncFileDescriptor & AsyncImageDescriptor handle extracting the ``key`` from this which is
        what is set against the field on the model.

        We need the AsyncFileInputData to pass across extra details that we may need - eg. width & height
        for image fields
        """
        value = data.get(name)
        try:
            value = json.loads(value)
            if value:
                return AsyncFileInputData.create_from_user_input(value)
            return value
        except JSONDecodeError:
            return value


class AsyncFileInputDataLengthValidator(validators.MaxLengthValidator):
    """Validate length of ``key`` on an AsyncFileInputData

    FileField passes ``max_length`` to the form field and the field is, at the database level,
    a char field. The normal FileField handles this internally but we can't extend forms.FileField
    as it expects to be handling File submissions which we aren't doing here. This validator
    just extracts the ``key`` and validates the length of that which is what gets written to the
    database.
    """

    def clean(self, x):
        if isinstance(x, AsyncFileInputData):
            # We want to check the length of the key which is what gets stored in db
            return len(x.name)
        return len(x)


@deconstructible
class AsyncFileInputDataValidator:
    """AsyncFileInputData has an error key that can be sent from the frontend - this validator just checks that"""

    def __call__(self, value):
        if isinstance(value, AsyncFileInputData):
            if value.error:
                raise ValidationError(f"There was an unexpected error: {value.error}")
        else:
            raise ValidationError("Bad input for file field")


class AsyncFileField(forms.Field):
    """Form field that renders a :class:`~alliance_platform.storage.async_uploads.models.AsyncFileInput`

    This is the default form field for :class:`alliance_platform.storage.async_uploads.models.AsyncFileField`
    """

    widget = AsyncFileInput

    async_field_registry: AsyncFieldRegistry
    async_field_id: str

    def __init__(
        self,
        *args,
        async_field_registry: AsyncFieldRegistry,
        async_field_id: str,
        storage: AsyncUploadStorage,
        max_length=None,
        **kwargs,
    ):
        """

        Args:
            *args: Any additional arguments to pass through to :class:`django.forms.Field`
            async_field_registry: The async field registry that should used on the frontend to create
                unique upload urls for files. This typically comes from :code:`field.async_field_registry` where :code:`field`
                is an :class:`~alliance_platform.storage.async_uploads.models.AsyncFileField`.
            async_field_id: The string ID of the field used in the registry. Generated with ``field.async_field_registry.generate_id(field)``.
            storage: The storage class. This comes from the field ``field.storage``.
            max_length: Max length for the filename
            **kwargs:ny additional keyword arguments to pass through to :class:`django.forms.Field`
        """
        self.async_field_registry = async_field_registry
        self.async_field_id = async_field_id
        # This comes from FileField
        self.max_length = max_length
        super().__init__(*args, **kwargs)

        # No way to pass args to a widget with how forms.Field work.. just
        # set it after creation
        self.widget.storage = storage

        if max_length is not None:
            self.validators.append(AsyncFileInputDataLengthValidator(int(max_length)))
        self.validators.append(AsyncFileInputDataValidator())

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs["async_field_registry"] = self.async_field_registry
        attrs["async_field_id"] = self.async_field_id
        return attrs


class AsyncImageField(AsyncFileField):
    widget = AsyncFileInput

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        if "accept" not in attrs:
            attrs.setdefault("accept", "image/*")
        if "list_type" not in attrs:
            attrs.setdefault("list_type", "picture")
        return attrs
