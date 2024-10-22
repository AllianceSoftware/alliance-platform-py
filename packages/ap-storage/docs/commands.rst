Management commands
===================

``cleanup_async_temp_files``
----------------------------

.. django-manage:: cleanup_async_temp_files

This command will delete old :class:`~alliance_platform.storage.async_uploads.models.AsyncTempFile` records. This is necessary
as a new record is created everytime an upload URL is requested from the frontend. If the upload then never occurs,
for whatever reason, then the record will hang around and never be cleaned up.

This command works by deleting items older than 48 hours by default, on the assumption that any URL generated before
that will no longer be used. You can change this with the ``--age`` option.

In addition to deleting the underlying database record, the `storage backend delete <https://docs.djangoproject.com/en/stable/ref/files/storage/#django.core.files.storage.Storage.delete>`_
method is also called, giving the backend the opportunity to delete any files from the storage backend itself. Any
errors here will be logged but otherwise ignored, on the assumption that in most cases the file won't actually exist
because the upload never occurred.

.. django-manage-option:: --age AGE_IN_HOURS

Only files older than this will be removed (in hours). Defaults to 48.

.. django-manage-option:: --quiet

Don't output anything - this includes number of items removed to stdout, and any files that could not be removed
from the underlying backend.
