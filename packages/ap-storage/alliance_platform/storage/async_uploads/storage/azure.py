from datetime import datetime
from datetime import timedelta
from typing import Any

from alliance_platform.storage.async_uploads.storage.base import AsyncUploadStorage
from alliance_platform.storage.async_uploads.storage.base import GenerateUploadUrlResponse
from alliance_platform.storage.settings import ap_storage_settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

try:
    from storages.backends.azure_storage import (  # type: ignore[import-untyped] # no types for storages
        AzureStorage,
    )
except ImportError as e:
    raise ImproperlyConfigured(
        "Optional dependency 'django-storages[azure]' is not installed. This is required for the AzureAsyncUploadStorage backend."
    ) from e

try:
    from azure.storage.blob import BlobClient
    from azure.storage.blob import BlobSasPermissions
    from azure.storage.blob import generate_blob_sas
except ImportError as e:
    raise ImproperlyConfigured(
        "Optional dependency 'azure-storage-blob' is not installed. This is required for the AzureAsyncUploadStorage backend."
    ) from e


class AzureAsyncUploadStorage(AzureStorage, AsyncUploadStorage):
    """Azure implementation of AsyncUploadStorage

    Uses signed URLs for uploading.
    """

    def generate_upload_url(
        self,
        name: str,
        field_id: str,
        *,
        expire: int = ap_storage_settings.UPLOAD_URL_EXPIRY,
        conditions: Any | None = None,
        fields: Any | None = None,
    ) -> GenerateUploadUrlResponse:
        """
        Generates a presigned PUT signed URL. Returns a dictionary with two elements: url and fields. Url is the url to post to. Fields is a dictionary filled with the form fields and respective values to use when submitting the post.

        ``conditions`` and ``fields`` currently ignored - here for compat with existing code that was written
        with S3 in mind

        Args:
            name:       the key for the upload
            expire:     time until presigned POST expires
            conditions: Ignored currently
            fields:     Ignored currently
        """
        # fields = fields.copy() if fields else {}
        # conditions = conditions.copy() if conditions else {}
        generate_blob_kwargs = {}
        # one of account_key or user_delegation_key must be passed; depending on auth method used will depend
        # whether `account_key` is set or not
        if self.account_key:
            generate_blob_kwargs["account_key"] = self.account_key
        else:
            generate_blob_kwargs["user_delegation_key"] = self.get_user_delegation_key(
                # internally this gets compared to a offset-naive date so we have to pass the same
                datetime.utcnow() + timedelta(seconds=expire)
            )
        credential = generate_blob_sas(
            self.account_name,
            self.azure_container,
            name,
            permission=BlobSasPermissions(create=True),
            expiry=timezone.now() + timedelta(seconds=expire),
            **generate_blob_kwargs,
        )
        container_blob_url = self.client.get_blob_client(name).url
        return {"url": BlobClient.from_blob_url(container_blob_url, credential=credential).url, "fields": {}}

    def generate_download_url(
        self, key: str, field_id: str, expire=ap_storage_settings.DOWNLOAD_URL_EXPIRY, **kwargs
    ):
        """
        Generates a signed URL to download the file.
        """

        return super().url(key, expire=expire, **kwargs)  # type: ignore[call-arg] # Not sure why this is an error... AzureStorage definitely supports expire

    def move_file(self, from_key, to_key):
        """Moves file by copying :code:`from_key` to :code:`to_key` and then deletes :code:`from_key`"""
        blob_client = self.client.get_blob_client(from_key)
        blob_url = blob_client.url
        to_blob_client = self.client.get_blob_client(to_key)
        response = to_blob_client.start_copy_from_url(blob_url)
        if response["copy_status"] == "success":
            blob_client.delete_blob()
