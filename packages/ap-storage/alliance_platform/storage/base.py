import datetime
import os
from typing import TYPE_CHECKING

from django.core.exceptions import SuspiciousFileOperation
from django.utils.crypto import get_random_string

if TYPE_CHECKING:
    # when doing type checks we can assume AsyncUploadStorage is used w/ an actual Storage as a mixin
    from django.core.files.storage import Storage
else:

    class Storage:
        pass


class AsyncUploadStorage(Storage):
    """Base storage class for use with :class:`~alliance_platform.storage.fields.async_file.AsyncFileField`

    Provides ``generate_upload_url`` to return a URL to upload a file to (eg. a signed URL) and a ``move_file`` method
    to move a file from a temporary location to the permanent location. The key used for temporary files is returned
    by ``generate_temporary_path`` and ``is_temporary_path`` should return whether a file is in the temporary location
    and needs to be moved to a permanent location.

    See :class:`~alliance_platform.storage.fields.async_file.AsyncFileMixin` for a detailed explanation of how
    all the pieces fit together.
    """

    #: The prefix to use on files when first uploaded before they are moved. This is used to identify a file as a
    #: temporary file to know whether to move them and so *must* be unique to temporary files.
    temporary_key_prefix = "async-temp-files"

    def generate_upload_url(self, name: str, **kwargs) -> str:
        """Should return a URL that a file can be uploaded directly to

        In S3 this would be a signed URL.
        """
        raise NotImplementedError("generate_upload_url must be implemented")

    def generate_download_url(self, key, **kwargs):
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