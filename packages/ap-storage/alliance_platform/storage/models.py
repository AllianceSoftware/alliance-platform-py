from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db import models

if TYPE_CHECKING:
    # circular imports
    from alliance_platform.storage.fields.async_file import AsyncFileField
    from alliance_platform.storage.fields.async_file import AsyncImageField


class AsyncTempFile(models.Model):
    """Model to track files that are being uploaded to a temporary location

    :class:`~alliance_platform.storage.views.GenerateUploadUrlView` is used to generate a URL to directly upload
    a file to. When this URL is generated an :class:`AsyncTempFile` is created to track the new
    key that is used (eg. /temp/2020/01/04/abc123-myfile.png), the original filename (eg. myfile.png)
    and the specific field it came from (this is done via :class:`alliance_platform.storage.registry.AsyncFieldRegistry`).

    Once a file has been uploaded and the form saved the key recorded here will be saved against the
    underlying file field (either :class:`~alliance_platform.storage.fields.async_file.AsyncFileField` or :class:`~alliance_platform.storage.fields.async_file.AsyncImageField`)
    on the target model which will check if that key is a temporary file using an :meth:`~alliance_platform.storage.base.AsyncUploadStorage.is_temporary_path`. If so the
    file will be moved to its permanent location using :meth:`~alliance_platform.storage.s3.S3AsyncUploadStorage.move_file`
    and the :class:`AsyncTempFile` record will have the ``moved_to_location`` value set. See :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin`
    for where this happens and more details.

    You must run the :class:`~alliance_platform.storage.management.commands.cleanup_async_temp_files` command periodically to
    cleanup this table. This handles two cases: the success case where ``moved_to_location`` is set but the record is
    being kept around for a while to detect duplicate submissions, and the other case where upload occurred on the frontend
    but the form was never submitted and the file was never moved.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.TextField()
    # This is the temporary location the file will be saved to and is generated using AsyncUploadStorage.generate_temporary_path(filename)
    key = models.CharField(max_length=500)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    field_name = models.CharField(max_length=100)
    # This will be set once the file has been moved to its permanent location. We store this so we can detect duplicate submissions and handle them appropriately.
    moved_to_location = models.TextField(blank=True)
    # This will be set if there was an error trying to move the file. When this is set cleanup_async_temp_files will not remove the record.
    error = models.TextField(null=True)

    @classmethod
    def create_for_field(cls, field: AsyncFileField | AsyncImageField, filename: str) -> AsyncTempFile:
        return AsyncTempFile.objects.create(
            original_filename=filename,
            content_type=ContentType.objects.get_for_model(field.model),
            field_name=field.name,
            key=field.storage.generate_temporary_path(filename, max_length=field.max_length),
        )

    class Meta:
        db_table = "alliance_platform_storage_async_temp_file"
