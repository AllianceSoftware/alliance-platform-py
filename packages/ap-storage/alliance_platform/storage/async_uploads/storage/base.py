import datetime
import os
from typing import TYPE_CHECKING
from typing import TypedDict

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import Storage
from django.urls import path
from django.utils.crypto import get_random_string

if TYPE_CHECKING:
    from alliance_platform.storage.async_uploads.registry import AsyncFieldRegistry


class GenerateUploadUrlResponse(TypedDict):
    #: The URL to post to
    url: str
    #: A dictionary of form field names and their values to be included when submitting
    fields: dict


class AsyncUploadStorage(Storage):
    """Base storage class for use with :class:`~alliance_platform.storage.async_uploads.models.AsyncFileField`

    Provides ``generate_upload_url`` to return a URL to upload a file to (eg. a signed URL) and a ``move_file`` method
    to move a file from a temporary location to the permanent location. The key used for temporary files is returned
    by ``generate_temporary_path`` and ``is_temporary_path`` should return whether a file is in the temporary location
    and needs to be moved to a permanent location.

    See :class:`~alliance_platform.storage.async_uploads.models.AsyncFileMixin` for a detailed explanation of how
    all the pieces fit together.
    """

    #: The prefix to use on files when first uploaded before they are moved. This is used to identify a file as a
    #: temporary file to know whether to move them and so *must* be unique to temporary files.
    temporary_key_prefix = "async-temp-files"

    def generate_upload_url(self, name: str, field_id: str, *args, **kwargs) -> GenerateUploadUrlResponse:
        """Should return a URL that a file can be uploaded directly to

        In S3 this would be a signed URL.
        """
        raise NotImplementedError("generate_upload_url must be implemented")

    def generate_download_url(self, key: str, field_id: str, **kwargs):
        """Should return a URL that the specified key should be downloadable from

        In S3 this would be a signed URL.
        """
        raise NotImplementedError("generate_download_url must be implemented")

    def move_file(self, from_key, to_key):
        """Move a file from one location to another

        The details of this depend on the storage solution. In S3 this involves copying the file
        and then deleting the original file.
        """
        raise NotImplementedError("move_file must be implemented")

    def generate_temporary_path(self, filename, max_length=None):
        """Generates a unique key to upload ``filename`` to

        This generates a string like ``async-temp-files/2021/03/03/fVy5cSVBQpOb-test.png`` where
        ``test.png`` is the ``filename`` passed in. The part after ``-`` will be truncated to fit within
        ``max_length`` but will retain the file extension. If there is insufficient length to
        accommodate the temporary path prefix (up to the ``-`` and the file extension an error
        will be thrown.
        """
        today = datetime.date.today().strftime("%Y/%m/%d")
        secret = get_random_string(12)
        prefix = f"{self.temporary_key_prefix}/{today}/{secret}-"
        if max_length:
            file_root, file_ext = os.path.splitext(filename)
            length_remaining = max_length - len(prefix) - len(file_ext)
            if length_remaining < 0:
                raise SuspiciousFileOperation(
                    f'Storage can not find an available temp filename for {filename}". '
                    "Please make sure that the corresponding file field "
                    'allows sufficient "max_length".'
                )
            truncation = len(file_root) - length_remaining
            if truncation > 0:
                file_root = file_root[:-truncation]
            filename = f"{file_root}{file_ext}"
        return f"{prefix}{filename}"

    def is_temporary_path(self, filename: str) -> bool:
        """Is the specified path that of a temporary file?

        This is used to determine whether a file should be moved to a permanent location. If this
        returns true it's expected an AsyncTempFile exists with the matching key.

        Default implementation checks if path begins with :code:`temporary_key_prefix`
        """
        if not filename:
            return False
        return filename.startswith(self.temporary_key_prefix + "/")

    def get_url_patterns(self, registry: "AsyncFieldRegistry"):
        """Return the URL patterns for any views required by the storage class

        When extending ``AsyncUploadStorage``, this method can be implemented if any custom views
        are required to support the implementation. By default, two views are supplied:

        1) :class:`~alliance_platform.storage.async_uploads.views.DownloadRedirectView` to support downloading an existing file. This
           is attached to the `"download-file/"` path.
        2) :class:`~alliance_platform.storage.async_uploads.views.GenerateUploadUrlView` to generate a URL that can be uploaded to
           directly from the frontend. This is attached to the `"generate-upload-url/"` path.

        This method is called by :meth:`~alliance_platform.storage.async_uploads.registry.AsyncFieldRegistry.get_url_patterns`.
        """
        from alliance_platform.storage.async_uploads.views import DownloadRedirectView
        from alliance_platform.storage.async_uploads.views import GenerateUploadUrlView

        # already generated patterns for these views, can return nothing
        if registry.attached_download_view and registry.attached_view:
            return []

        return [
            path("download-file/", DownloadRedirectView.as_view(registry=registry)),
            path("generate-upload-url/", GenerateUploadUrlView.as_view(registry=registry)),
        ]
