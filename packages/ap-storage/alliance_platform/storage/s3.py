from typing import Any

from alliance_platform.storage.storage import AsyncUploadStorage
from storages.backends.s3boto3 import S3Boto3Storage


class S3AsyncUploadStorage(S3Boto3Storage, AsyncUploadStorage):
    """S3 implementation of AsyncUploadStorage

    Uses signed URLs for uploading.
    """

    # if the bucket is public and you don't want a querystring attached, set this to False.
    querystring_auth = True

    def generate_upload_url(
        self, name: str, expire: int | None = 3600, conditions: Any | None = None, fields: Any | None = None
    ) -> str:  # type: ignore[override] # Specific kwargs for s3
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

    def generate_download_url(self, key, **kwargs):
        """Generates a signed URL to download the file"""
        return super().url(key)

    def move_file(self, from_key, to_key):
        """Moves file by copying :code:`from_key` to :code:`to_key` and then deletes :code:`from_key`"""
        object = {"Bucket": self.bucket_name, "Key": from_key}
        client = self.bucket.meta.client
        client.copy(object, self.bucket_name, to_key)
        client.delete_object(**object)
