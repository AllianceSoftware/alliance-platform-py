from typing import Any

from alliance_platform.storage.async_uploads.storage.base import AsyncUploadStorage
from alliance_platform.storage.async_uploads.storage.base import GenerateUploadUrlResponse
from alliance_platform.storage.settings import ap_storage_settings
from django.core.exceptions import ImproperlyConfigured

try:
    from storages.backends.s3 import S3Storage  # type: ignore[import-untyped] # no types for storages
except ImportError as e:
    raise ImproperlyConfigured(
        "Optional dependency 'django-storages[s3]' is not installed. This is required for the S3AsyncUploadStorage backend."
    ) from e


class S3AsyncUploadStorage(S3Storage, AsyncUploadStorage):
    """S3 implementation of AsyncUploadStorage

    Uses signed URLs for uploading.
    """

    # if the bucket is public and you don't want a querystring attached, set this to False.
    querystring_auth = True

    def generate_upload_url(
        self,
        name: str,
        field_id: str,
        *,
        expire: int | None = ap_storage_settings.UPLOAD_URL_EXPIRY,
        conditions: Any | None = None,
        fields: Any | None = None,
    ) -> GenerateUploadUrlResponse:
        """
        Generates a presigned POST signed URL. Returns a dictionary with two elements: url and fields. Url is the url to post to. Fields is a dictionary filled with the form fields and respective values to use when submitting the post.
        e.g

        .. code-block:: json

            {
                "url": "https://mybucket.s3.amazonaws.com",
                "fields": {
                    "acl": "public-read",
                    "key": "mykey",
                    "signature": "mysignature",
                    "policy": "mybase64 encoded policy"
                }
            }

        Args:
            name:       the key for the upload
            expire:     time until presigned POST expires
            conditions: A list of conditions to include in the policy. See https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.generate_presigned_post for valid values.
                        Conditions that are included may pertain to acl, content-length-range, Cache-Control, Content-Type, Content-Disposition, Content-Encoding, Expires, success_action_redirect, redirect, success_action_status, and/or x-amz-meta-.
            fields:     A dictionary of prefilled form fields to build on top of.
                        Elements that may be included are acl, Cache-Control, Content-Type, Content-Disposition, Content-Encoding, Expires, success_action_redirect, redirect, success_action_status, and x-amz-meta-.
                        See https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.generate_presigned_post for valid values.
        """
        fields = fields.copy() if fields else {}
        conditions = conditions.copy() if conditions else {}
        return self.bucket.meta.client.generate_presigned_post(
            self.bucket_name, name, Fields=fields, Conditions=conditions, ExpiresIn=expire
        )

    def generate_download_url(
        self, key: str, field_id: str, expire=ap_storage_settings.DOWNLOAD_URL_EXPIRY, **kwargs
    ):
        """
        Generates a signed URL to download the file.
        """

        return super().url(key, expire=expire, **kwargs)  # type: ignore[call-arg] # Not sure why this is an error... S3Storage definitely supports expire

    def move_file(self, from_key, to_key):
        """Moves file by copying :code:`from_key` to :code:`to_key` and then deletes :code:`from_key`"""
        object = {"Bucket": self.bucket_name, "Key": from_key}
        client = self.bucket.meta.client
        client.copy(object, self.bucket_name, to_key)
        client.delete_object(**object)
