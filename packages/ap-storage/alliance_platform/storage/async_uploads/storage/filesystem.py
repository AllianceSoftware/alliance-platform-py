import os
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from alliance_platform.storage.async_uploads.storage.base import AsyncUploadStorage
from alliance_platform.storage.async_uploads.storage.base import GenerateUploadUrlResponse
from django.core.files.move import file_move_safe
from django.core.files.storage import FileSystemStorage
from django.core.signing import TimestampSigner
from django.urls import path
from django.urls import reverse

if TYPE_CHECKING:
    # circular imports
    from alliance_platform.storage.async_uploads.registry import AsyncFieldRegistry


class FileSystemAsyncUploadStorage(FileSystemStorage, AsyncUploadStorage):
    """Implementation of AsyncUploadStorage that uploads directly to the local server

    This is useful in local dev, or when you still want the behaviour of uploading immediately rather than waiting
    until the whole form is submitted.

    To use this by default, set the :setting:`STORAGES <django:STORAGES>` setting::

        STORAGES = {
            "default": {
                "BACKEND": "alliance_platform.storage.async_uploads.storage.filesystem.FileSystemAsyncUploadStorage"
            },
        }

    Alternatively, pass an instance of the class to the ``storage`` argument on :class:`~alliance_platform.storage.async_uploads.models.AsyncFileField`
    or :class:`~alliance_platform.storage.async_uploads.models.AsyncImageField`.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.signer = TimestampSigner()
        # This is only available in >= Django 5.1.
        if not hasattr(self, "_allow_overwrite"):
            self._allow_overwrite = False

    def generate_upload_url(self, name: str, field_id: str, *args, **kwargs) -> GenerateUploadUrlResponse:
        """
        Generates a signed URL that the frontend can use to upload a file directly to the server.
        """
        signed_path = self.signer.sign(name)
        query_params = urlencode({"path": signed_path, "field_id": field_id})
        upload_url = reverse("file_system_async_storage_upload") + f"?{query_params}"
        return {"url": upload_url, "fields": {}}

    def generate_download_url(self, key: str, field_id: str, **kwargs):
        signed_path = self.signer.sign(key)
        query_params = urlencode({"path": signed_path, "field_id": field_id})
        upload_url = reverse("file_system_async_storage_download") + f"?{query_params}"
        return upload_url

    def move_file(self, from_key, to_key):
        """
        Moves a file from the temporary location to the permanent location.
        """
        # Create any intermediate directories that do not exist.
        full_path = self.path(to_key)

        # This logic for creating dirs is taken from FileSystemStorage._save
        directory = os.path.dirname(full_path)
        try:
            if self.directory_permissions_mode is not None:
                # Set the umask because os.makedirs() doesn't apply the "mode"
                # argument to intermediate-level directories.
                old_umask = os.umask(0o777 & ~self.directory_permissions_mode)
                try:
                    os.makedirs(directory, self.directory_permissions_mode, exist_ok=True)
                finally:
                    os.umask(old_umask)
            else:
                os.makedirs(directory, exist_ok=True)
        except FileExistsError:
            raise FileExistsError("%s exists and is not a directory." % directory)
        file_move_safe(self.path(from_key), full_path, allow_overwrite=self._allow_overwrite)

    def get_url_patterns(self, registry: "AsyncFieldRegistry"):
        patterns = super().get_url_patterns(registry)
        from alliance_platform.storage.async_uploads.views.filesystem import (
            FileSystemAsyncStorageDownloadView,
        )
        from alliance_platform.storage.async_uploads.views.filesystem import FileSystemAsyncStorageUploadView

        # already generated patterns for these views, can return nothing
        if getattr(registry, FileSystemAsyncStorageUploadView.registration_attach_key, None):
            return patterns

        return [
            *patterns,
            path(
                "upload-file-direct/",
                FileSystemAsyncStorageUploadView.as_view(registry=registry),
                name="file_system_async_storage_upload",
            ),
            path(
                "download-file-direct/",
                FileSystemAsyncStorageDownloadView.as_view(registry=registry),
                name="file_system_async_storage_download",
            ),
        ]
