from __future__ import annotations

from dataclasses import dataclass
from hashlib import shake_256
import json
from json import JSONDecodeError
import logging
import mimetypes
from typing import TYPE_CHECKING
from typing import Protocol
from typing import TypedDict
from typing import cast
from urllib.parse import urlencode

from alliance_platform.storage.models import AsyncTempFile
from alliance_platform.storage.registry import AsyncFieldRegistry
from alliance_platform.storage.registry import default_async_field_registry
from alliance_platform.storage.storage import AsyncUploadStorage
from allianceutils.middleware import CurrentRequestMiddleware
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.db.models import FileField
from django.db.models import ImageField
from django.db.models import Model
from django.db.models import Q
from django.db.models import signals
from django.db.models.fields.files import FieldFile
from django.db.models.fields.files import FileDescriptor
from django.db.models.fields.files import ImageFieldFile
from django.forms.widgets import Input
from django.urls import reverse
from django.utils.deconstruct import deconstructible
from django_site_core.auth import resolve_perm_name

logger = logging.getLogger("alliance_platform.storage")


if TYPE_CHECKING:

    class AsyncFileMixinProtocol(Protocol):
        model: models.Model

        def contribute_to_class(self, cls: type[Model], name: str, private_only: bool = ...) -> None: ...

        def __init__(self, *args, max_length: int | None, **kwargs) -> None: ...

    class FieldFileMixinProtocol(Protocol):
        instance: models.Model
        name: str | None
        field: AsyncFileField | AsyncImageField

else:

    class AsyncFileMixinProtocol:
        pass

    class FieldFileMixinProtocol:
        pass


class AsyncFileModelRegistry:
    """Class that tracks files on a model and handles moving files on save

    When the save occurs all temporary files will be moved to final location and a
    single save will be done on the record to write the final field values to the db.
    All AsyncTempFiles that are no longer needed will be deleted in a single query.

    If any error occurs on a move then it is logged to the alliance_platform.storage logger and
    the AsyncTempFile is retained with the ``error`` field set. This can then be manually
    followed up. The cleanup_async_temp_files management command will not remove these
    files.
    """

    fields: list[AsyncFileField | AsyncImageField]
    _save_in_progress: list[Model]

    def __init__(self):
        self.fields = []
        self._save_in_progress = []

    @classmethod
    def register_field(cls, model_class: type[Model], field: AsyncFileField | AsyncImageField):
        key = "__async_file_model_registry"
        if not hasattr(model_class, key):
            registry = AsyncFileModelRegistry()
            setattr(model_class, key, registry)
            signals.post_save.connect(registry._move_temp_files_into_place, sender=model_class)
        else:
            registry = getattr(model_class, key)
        registry.fields.append(field)

    def _move_temp_files_into_place(self, instance, *args, **kwargs):
        """For each async file on the instance move them from temporary location to permanent location

        This is triggered by the ``post_save`` signal. The destination filename goes through the normal
        FileField logic using ``AsyncTempFile.original_filename``. If ``FileField`` has ``upload_to`` set
        then this will be used, otherwise the destination will be the same as ``original_filename``.

        If the destination filename is too long for the database after ``upload_to`` is applied then the
        file will be truncated by the ``Storage.get_available_name`` method.

        Also see :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.move_file`

        This uses as few queries as possible to do the moves and update new values. Only async fields
        that have a temporary key are touched - other fields that have already been moved are left
        alone.
        """
        # Use ``is`` like this instead of ``instance in self._save_in_progress`` so we check object is same not just _pk
        if [x for x in self._save_in_progress if x is instance]:
            return
        _filter = Q()
        for field in self.fields:
            file = getattr(instance, field.name)
            _filter |= Q(
                key=file.name,
                content_type=ContentType.objects.get_for_model(field.model),
                field_name=field.name,
            )
        with transaction.atomic():
            temp_files_qs = AsyncTempFile.objects.filter(_filter).select_for_update()
            temp_files = {file.field_name: file for file in temp_files_qs}
            pending_save: list[AsyncTempFile] = []
            should_save = False
            for field in self.fields:
                file = getattr(instance, field.name)
                if field.storage.is_temporary_path(file.name):
                    try:
                        temp_file = temp_files[field.name]
                    except KeyError:
                        # This is unexpected. Could mean file was cleaned up manually before submission occurred.
                        logger.error(
                            f"{file.name} is a temporary file path in {field.storage.__class__.__name__} but no matching "
                            f"AsyncTempFile with that key could be found. File cannot be moved to its permanent location. "
                            f"See record {instance.__class__.__name__}(pk={instance.pk})"
                        )
                    else:
                        try:
                            if temp_file.moved_to_location:
                                file.name = temp_file.moved_to_location
                                try:
                                    request = CurrentRequestMiddleware.get_request()
                                    url = request.get_full_path() if request else "(unknown)"
                                except Exception:
                                    url = "(unknown)"
                                logger.warning(
                                    f"Temp file for has already been moved to its final location using stored destination for field value ('{file.name}'). This happens "
                                    "when a form is submitted multiple times and likely indicates a bug in the form that should be resolved. "
                                    f"Error occurred on URL {url}. See record {instance.__class__.__name__}(pk={instance.pk}), field '{field.name}'"
                                )
                            else:
                                target_path = field.generate_filename(instance, temp_file.original_filename)
                                if field.max_length:
                                    target_path = field.storage.get_available_name(
                                        target_path, max_length=field.max_length
                                    )
                                field.storage.move_file(file.name, target_path)
                                file.name = target_path
                                temp_file.moved_to_location = target_path
                                pending_save.append(temp_file)
                        except Exception:
                            logger.error(
                                f"{file.name} is a temporary file path in {field.storage.__class__.__name__} but moving it "
                                f"to its permanent location failed. File has not been moved and record has temporary key still set. "
                                f"See record {instance.__class__.__name__}(pk={instance.pk}) and AsyncTempFile(pk={temp_file.pk}). "
                                f"AsyncTempFile will not be deleted.",
                                exc_info=True,
                            )
                            import traceback

                            temp_file.error = traceback.format_exc()
                            temp_file.save()
                        else:
                            field.before_move_file(instance)
                            setattr(instance, field.name, file)
                            should_save = True
            if not should_save:
                return

            self._save_in_progress.append(instance)
            try:
                instance.save()
                AsyncTempFile.objects.bulk_update(pending_save, ["moved_to_location"])
            finally:
                self._save_in_progress = list(filter(lambda x: x is not instance, self._save_in_progress))


# by default cap to 100MiB
default_max_size = 100
# Default max_length on underlying CharField. Note that changing this after fields exist won't be detected by djangos migration system
default_max_length = 500


class AsyncFileMixin(AsyncFileMixinProtocol):
    """Mixin for file fields that works with :class:`~alliance_platform.storage.storage.AsyncUploadStorage` to
    handle uploading directly to external service like S3 or Azure.

    This field works in conjunction with :class:`~alliance_platform.storage.views.GenerateUploadUrlView`. The view will
    generate a URL (eg. a signed URL when using S3) that the frontend can then upload to. Each view is tied
    to a specific registry which you can specify in ``async_field_registry`` (defaults to :data:`~alliance_platform.storage.registry.default_async_field_registry`).

    The permissions used by :class:`~alliance_platform.storage.views.GenerateUploadUrlView` can be specified in
    ``perm_create`` and ``perm_update``. If not provided they default to the value returned by :meth:`django_site_core.auth.resolve_perm_name`
    for the action 'create' and 'update' respectively.

    When using django forms :class:`~alliance_platform.storage.fields.async_file.AsyncFileFormField` provides a widget for handling
    the upload from the frontend. This is the default ``formfield`` provided by :class:`~alliance_platform.storage.fields.async_file.AsyncFileField`.

    .. note:: The key for the file is stored in the database as a CharField and as such has a max_length. The default
        for this is ``500``. This must be sufficient to accommodate the temporary file value which looks something like
        ``async-temp-files/2021/03/03/fVy5cSVBQpOb-test.png`` by default (see :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.generate_temporary_path`
        for how to customise this).

        Anything after the ``-`` will be truncated if necessary for the purposes of the temporary key. The actual filename
        will still be used for the final field value after the temporary file is moved to the permanent location. When
        moving to the permanent location the filename may be truncated if the length is too long when ``upload_to`` is
        taken into account.

        If using :class:`~alliance_platform.storage.s3.S3AsyncUploadStorage` you may wish to set ``AWS_S3_FILE_OVERWRITE = False`` to avoid overwriting files
        if the same key is used. This is not necessary if your files generate unique paths (eg. ``upload_to`` takes into
        account the record ID and filename).

    The flow for how this works is as follows:

        1) When a form is rendered on the frontend (eg. using :class:`~alliance_platform.storage.fields.async_file.AsyncFileFormField`) it
           knows the ``async_field_id`` from the registry and ``generate_upload_url`` which is to the :class:`~alliance_platform.storage.views.GenerateUploadUrlView`
           view for the registry. This URL will be used to generated a specific URL for each file to upload to.

        2) When an upload occurs on the frontend it first hits ``generate_upload_url`` and passes the ``async_field_id``, the filename
           and optionally an ``instance_id`` if it's an update for an existing record. :class:`~alliance_platform.storage.views.GenerateUploadUrlView`
           looks up the registry for the ``async_field_id`` to get the field and checks permissions on it (``perm_update`` if
           ``instance_id`` is passed otherwise ``perm_create``). If the permission check passes it will then create a
           :class:`~alliance_platform.storage.models.AsyncTempFile` record to track the ``filename`` passed in and a :meth:`generated key <alliance_platform.storage.storage.AsyncUploadStorage.generate_temporary_path>`
           that will be used to upload the file to a temporary location on the storage backend. The view will return an
           upload url by calling :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.generate_upload_url` along with the generated ``key``.

        3) The frontend will receive the ``upload_url`` and ``key`` and proceed to upload to it. When the form is submitted
           and saved the ``key`` (the value returned from :meth:`generated key <alliance_platform.storage.storage.AsyncUploadStorage.generate_temporary_path>`)
           is the what will be stored in the database.

        4) On save a ``post_save`` signal will be called which will check if the file needs to be moved to a permanent
           location. It does this by calling :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.is_temporary_path` and
           :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.move_file` is called to move the file to its permanent
           location at which point the ``AsyncTempFile`` is deleted.

        5) If an upload occurs but the form isn't submitted :class:`~alliance_platform.storage.models.AsyncTempFile` will be created
           but never deleted. The :class:`~alliance_platform.storage.management.commands.cleanup_async_temp_files` should be run
           periodically to clean these up.

    The url returned when accessing the ``url`` property, eg. ``model.file_field.url`` will always return the URL for
    :class:`~alliance_platform.storage.views.DownloadRedirectView`. This view will check the user has permission to download the
    file by checking the ``perm_download`` permission. If not provided this defaults to the value returned by
    :meth:`django_site_core.auth.resolve_perm_name` with the action "detail" (ie. if they have permission to view the record
    they can download the file). This view will then redirect to the URL provided by
    :meth:`~alliance_platform.storage.storage.AsyncUploadStorage.generate_download_url`.

    .. note:: You must you this with a storage class that implements :class:`~alliance_platform.storage.storage.AsyncUploadStorage`.
        Either set DEFAULT_FILE_STORAGE to a class (eg. :class:`~alliance_platform.storage.s3.S3AsyncUploadStorage`) or pass an
        instance in the ``storage`` kwarg.

    For use with a Presto form use :class:`~alliance_platform.storage.drf.serializer.AsyncFileField` or :class:`~alliance_platform.storage.drf.serializer.AsyncImageField`
    on your serializer. This is handled by default when extending :class:`xenopus_frog_app.base.XenopusFrogAppModelSerializer`.
    Codegen will create this as a ``AsyncFileField`` or ``AsyncImageField`` on the frontend Presto model.
    ``getWidgetForField`` will map these fields to the ``UploadWidget``.

    See :class:`~alliance_platform.storage.fields.async_file.AsyncFileField` and :class:`~alliance_platform.storage.fields.async_file.AsyncFileField`
    for Field classes that use this.

    .. warning:: User input should be assigned using the :class:`~alliance_platform.storage.fields.async_file.AsyncFileInputData` class
        which has validation to disallow things like moving the file by changing the key that passed from the frontend. This
        is handled for you when using :class:`~alliance_platform.storage.fields.async_file.AsyncFileField`,
        :class:`~alliance_platform.storage.fields.async_file.AsyncImageField`, :class:`~alliance_platform.storage.drf.serializer.AsyncFileField`
        or :class:`~alliance_platform.storage.drf.serializer.AsyncImageField`

    If a file cannot be moved for any reason (eg. any exception is raised) then the error will be saved in the
    ``error`` field on the :class:`~alliance_platform.storage.models.AsyncTempFile` record and the temporary key will be retained as
    the field value. The error will also be logged to the ``alliance_platform.storage`` logger. This cannot be resolved automatically
    and so requires manual intervention to cleanup.

    File size can be restricted by passing in ``max_size`` (in MB)

    The file extension/file type can be restricted by passing in ``file_restrictions`` for example:

    .. code-block:: python

        ["image/png"]
        ["image/*"]
        [".doc", "docx"]
        ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"]

    """

    storage: AsyncUploadStorage

    def __init__(
        self,
        *args,
        perm_create=None,
        perm_update=None,
        perm_detail=None,
        max_size=default_max_size,
        file_restrictions=None,
        async_field_registry=default_async_field_registry,
        max_length=default_max_length,
        **kwargs,
    ):
        super().__init__(*args, max_length=max_length, **kwargs)  # type: ignore[safe-super]
        if not isinstance(self.storage, AsyncUploadStorage):
            raise ValueError(
                "When using AsyncFileMixin the file storage class must extend AsyncUploadStorage. Either set DEFAULT_FILE_STORAGE or pass the 'storage' kwarg"
            )
        self.perm_create = perm_create
        self.perm_update = perm_update
        self.perm_detail = perm_detail
        self.max_size = max_size
        if isinstance(file_restrictions, str):
            file_restrictions = [file_restrictions]
        elif not file_restrictions:
            file_restrictions = []
        self.file_restrictions = file_restrictions
        self.async_field_registry = async_field_registry

    def contribute_to_class(self, cls, name: str, private_only: bool = False):
        super().contribute_to_class(cls, name, private_only=private_only)  # type: ignore[safe-super]
        if not cls._meta.abstract and self.model._meta.app_config:
            field = cast(AsyncFileField, self)
            AsyncFileModelRegistry.register_field(cls, field)
            self.async_field_registry.register_field(field)
            if not self.perm_update:
                self.perm_update = resolve_perm_name(
                    app_config=self.model._meta.app_config,
                    model=self.model,
                    action="update",
                    is_global=False,
                )
            if not self.perm_create:
                self.perm_create = resolve_perm_name(
                    app_config=self.model._meta.app_config,
                    model=self.model,
                    action="create",
                    is_global=True,
                )

            if not self.perm_detail:
                self.perm_detail = resolve_perm_name(
                    app_config=self.model._meta.app_config,
                    model=self.model,
                    action="detail",
                    is_global=False,
                )

    def is_valid_filetype(self, filename):
        if not self.file_restrictions:
            return True
        mimetype, _ = mimetypes.guess_type(filename)
        for restriction in self.file_restrictions:
            # special cases for /*
            if restriction in ("image/*", "video/*", "audio/*"):
                if mimetype and mimetype.startswith(restriction[:-1]):
                    return True
            elif restriction.startswith("."):
                # filename restriction
                if filename.lower().endswith(restriction.lower()):
                    return True
            elif mimetype == restriction:
                return True
        return False

    def before_move_file(self, instance):
        """Hook to do something before file is moved."""
        pass


class AsyncFileInputDataKwargs(TypedDict, total=False):
    key: str
    name: str
    width: int | None
    height: int | None
    error: str | None


@dataclass
class AsyncFileInputData:
    """The data we receive from the frontend gets converted to an instance of this

    :code:`width` and :code:`height` can optionally be included for images to avoid having
    to calculate dimensions manually when an :class:`~alliance_platform.storage.fields.async_file.AsyncImageField` uses the
    ``width_field`` and ``height_field`` options.
    """

    # The key the file was uploaded to
    key: str
    # The original name of the file
    name: str
    # The width of the image (optional - only applicable to :class:`~alliance_platform.storage.fields.async_file.AsyncImageField`)
    width: int | None = None
    # The height of the image (optional - only applicable to :class:`~alliance_platform.storage.fields.async_file.AsyncImageField`)
    height: int | None = None
    # Only set if there was an upload error on the frontend
    error: str | None = None

    def update_dimension_cache(self, field: models.Field):
        """Updates the dimension_cache on :class:`~alliance_platform.storage.fields.async_file.AsyncImageField`"""

        width = self.width
        height = self.height
        if width and height:
            # See AsyncImageField.dimension_cache. We do this rather than
            # assigning directly to the width + height fields on instance
            # as when creating a new instance by passing in kwargs then
            # the width + height fields may be set to the the defaults
            # (eg. None) after this runs which would override the values.
            # For example the first assignment would work if we did that
            # but the second where arguments are passed in __init__ may
            # not depending on the order of fields on the model
            # # Works
            # tm = AsyncFileTestModel()
            # tm.image_with_dims = AsyncFileInputData(key="test.png", name="test.png", width=16, height=16)
            # # No luck.. width/height get set to None after image_with_dims __set__ runs
            # tm = AsyncFileTestModel(
            #     image_with_dims=AsyncFileInputData(key="test.png", name="test.png", width=16, height=16)
            # )
            # Instead we cache it on the field and `update_dimension_fields`
            # checks for it otherwise falls back to the default ImageField
            # behaviour.
            setattr(field, "dimension_cache", (width, height))

    @classmethod
    def create_from_user_input(cls, values: dict[str, str | int]):
        """Create instance from user input.

        Throws if invalid keys present in ``values``. ``url`` is accepted but ignored."""
        data: AsyncFileInputDataKwargs = {}
        valid_fields = ["key", "name", "width", "height", "error"]
        # We return "url" in format_value but it's not something
        # that is relevant in submission. Remove it here so frontend
        # implementations don't need to worry about it.
        ignore_fields = ["url"]
        invalid_input = []
        for field, value in values.items():
            if field in valid_fields:
                data[field] = values[field]  # type: ignore[literal-required] # mypy issue #7178
            elif field not in ignore_fields:
                invalid_input.append(field)
        if invalid_input:
            raise ValidationError(f"Invalid input keys received: {', '.join(invalid_input)}")
        return cls(**data)

    def validate_key(self, field: AsyncFileField, existing_value: str | AsyncFieldFile | None):
        """Validate the key should be accepted

        This checks to make sure the key is a temporary path or matches the existing field
        value. This prevents manipulation of keys which could result in eg. taking over another records file
        """
        if not field.storage.is_temporary_path(self.key):
            existing_key = existing_value
            if isinstance(existing_value, AsyncFieldFile):
                existing_key = cast(
                    str, existing_value.name
                )  # mypy: seems like it cant infer from property 'name' but IDE can
            if existing_key != self.key:
                logger.error(
                    f"{self.key} was received but is NOT a temporary file path and does not match "
                    f"the current value {existing_value}. This could mean the upload was manipulated "
                    f"to attempt to reference a different records file. This action has been blocked "
                    f"with a validation error."
                )
                raise ValidationError({field.name: "Invalid upload received"})


# This does not extend FileInput as we don't actually receive a file
# from the frontend. Instead we get a string which represents the key
# for the storage backend.
class AsyncFileInput(Input):
    """Input that renders the React component UploadWidget

    This handles the submission value from UploadWidget and converts it to an instance
    of :class:`~alliance_platform.storage.fields.async_file.AsyncFileInputData`. This is then handled
    on the descriptor classes for :class:`~alliance_platform.storage.fields.async_file.AsyncFileField`
    and :class:`~alliance_platform.storage.fields.async_file.AsyncImageField`.
    """

    input_type = "async-file"
    template_name = "widgets/async_file_input.html"

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


class AsyncFileFormField(forms.Field):
    """Form field that renders a :class:`~alliance_platform.storage.fields.async_file.AsyncFileInput`

    This is the default form field for :class:`alliance_platform.storage.fields.async_file.AsyncFileField`
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
                is an :class:`~alliance_platform.storage.fields.async_file.AsyncFileField`.
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


class AsyncImageFormField(AsyncFileFormField):
    widget = AsyncFileInput

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        if "accept" not in attrs:
            attrs.setdefault("accept", "image/*")
        if "list_type" not in attrs:
            attrs.setdefault("list_type", "picture")
        return attrs


class FieldFileMixin:
    @property
    def url(self: FieldFileMixinProtocol):
        if not self.name:
            raise ValueError(f"`.url()` called on {self} but {self} is empty")

        # URL downloads all go through a DownloadRedirectView so we can do perm checks
        # See AsyncUploadStorage.generate_download_url for where the actual URL generation occurs.
        url = reverse(self.field.async_field_registry.attached_download_view)
        query = urlencode(
            {
                "field_id": self.field.async_field_registry.generate_id(self.field),
                "instance_id": self.instance.pk,
                # this is here to cache bust when an image is modified
                # assuming AWS_S3_FILE_OVERWRITE is false then even if you upload a
                # file with the same name into the same field, it will have a different name
                # hash is taken to avoid exposing the name to frontend which otherwise isn't
                # done until download view verifies permissions
                "_": shake_256(self.name.encode()).hexdigest(8),
            }
        )
        return f"{url}?{query}"


class AsyncFileDescriptor(FileDescriptor):
    """Extracts the ``key`` from AsyncFileInputData to be set against instance"""

    def __set__(self, instance, value):
        if isinstance(value, AsyncFileInputData):
            value.validate_key(cast(AsyncFileField, self.field), instance.__dict__.get(self.field.name))
            value = value.key
        super().__set__(instance, value)


class AsyncFieldFile(FieldFileMixin, FieldFile):
    pass


class AsyncFileField(AsyncFileMixin, FileField):  # type: ignore[misc] # mypy dont like the fact that we're using AsyncUploadStorage and report it as conflict w/ FileField
    """A FileField that works with AsyncUploadStorage to directly upload somewhere (eg. S3) from the frontend

    See :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin` for more details on how this field works.
    """

    attr_class = AsyncFieldFile
    descriptor_class = AsyncFileDescriptor

    def formfield(self, **kwargs):  # type: ignore[override] # can fix this with *args, but the implementation of FileField.formfield only accepts kwargs so I'll just follow it's implementation
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
    :meth:`alliance_platform.storage.fields.async_file.AsyncImageField.update_dimension_fields`.
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
    :class:`~alliance_platform.storage.fields.async_file.AsyncImageFormField` form field (the default). This works in
    conjunction with the ``UploadWidget`` on the frontend.

    2) (slow) Same behaviour as :class:`~django.db.models.ImageField` which requires the file to be downloaded
    and processed with Pillow.

    See :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin` for more details on how this field works.
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

    def formfield(self, **kwargs):  # type: ignore[override] # can fix this with *args, but the implementation of FileField.formfield only accepts kwargs so I'll just follow it's implementation
        return super().formfield(
            **{
                "form_class": AsyncImageFormField,
                "async_field_id": self.async_field_registry.generate_id(self),
                "async_field_registry": self.async_field_registry,
                "storage": self.storage,
                **kwargs,
            }
        )
