Usage
=====

To use these fields you must be using an :class:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage` storage class at either
the global level, or field level. To setup globally see the :doc:`installation` instructions.

To use at a field level create a storage class and pass it to the field:

.. code:: python

    storage = S3AsyncUploadStorage()

    class MyModel(models.Model):
        file = AsyncFileField(storage=storage)
        image = AsyncImageField(storage=storage)

In addition to that two views need to be registered. :class:`~alliance_platform.storage.async_uploads.views.GenerateUploadUrlView` is used to
generate a URL for the frontend to upload to (eg. a signed S3 URL). :class:`~alliance_platform.storage.async_uploads.views.DownloadRedirectView`
is used to check a user has permissions on a file before redirecting to the download location (eg. a signed S3 URL). This
is covered in the :doc:`installation` guide.

Usage
#####

All usages require a model - there's currently no support for uploading files without the result being saved
to an :class:`~alliance_platform.storage.async_uploads.models.AsyncFileField` or :class:`~alliance_platform.storage.async_uploads.models.AsyncImageField`.

The default template setup will work automatically for files in both django forms and Presto forms. Uploading
is performed using the UploadWidget on the frontend (see UploadWidget.tsx).

For a deeper understanding of how django forms work see :class:`~alliance_platform.storage.async_uploads.forms.AsyncFileField`
and :class:`~alliance_platform.storage.async_uploads.forms.AsyncFileInput`.

async_uploads.rest_framework integration requires you to use the async_uploads.rest_framework fields
:class:`alliance_platform.storage.async_uploads.rest_framework.AsyncFileField` or
:class:`alliance_platform.storage.async_uploads.rest_framework.AsyncFileField`. See :ref:`storage-serializer-fields` for how to set
this as a default.

Intermediate files are stored in the :class:`alliance_platform.storage.async_uploads.models.AsyncTempFile` table. This should be periodically
cleaned up by running the :class:`~alliance_platform.storage.management.commands.cleanup_async_temp_files` command.
