Async File Uploads
==================

Overview
--------

The Async Upload feature in alliance-platform-storage provides a seamless way to handle asynchronous file uploads in Django applications.
In this context, the async in "Async Upload" means the file is immediately uploaded to the server (e.g. S3, Azure, local server) while the user
continues to fill out a form. A reference (the key) to the uploaded file is stored in the form and handled in the Django model save when
processing the form submission. See `How it works`_ for more specifics.

It's primarily implemented through the :class:`~alliance_platform.storage.async_uploads.models.AsyncFileField` and :class:`~alliance_platform.storage.async_uploads.models.AsyncImageField` classes.


Key Components:
^^^^^^^^^^^^^^^

1. :class:`~alliance_platform.storage.async_uploads.models.AsyncFileField`: The main field for handling async file uploads.
2. :class:`~alliance_platform.storage.async_uploads.models.AsyncImageField`: Similar to AsyncFileField, but specifically for image files.
3. :class:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage`: The base storage class for handling async uploads.
4. :class:`~alliance_platform.storage.async_uploads.views.GenerateUploadUrlView`: View for generating upload URLs.
5. :class:`~alliance_platform.storage.async_uploads.views.DownloadRedirectView`: View for handling file downloads.
6. :class:`~alliance_platform.storage.async_uploads.registry.AsyncFieldRegistry`: Registry for managing async fields.

.. _async-upload-backends:

Storage backends:
^^^^^^^^^^^^^^^^^

Storage backends handle the logic for generating signed upload & download URLs, and for moving files to the final
location. The following backends are provided:

1. :class:`~alliance_platform.storage.async_uploads.storage.s3.S3AsyncUploadStorage` - Uploads to Amazon S3
2. :class:`~alliance_platform.storage.async_uploads.storage.azure.AzureAsyncUploadStorage` - Uploads to Azure blob storage
3. :class:`~alliance_platform.storage.async_uploads.storage.filesystem.FileSystemAsyncUploadStorage` - Uploads to Django directly and stores the file in the local filesystem (e.g. media files).

Other implementations can be provided by extending the :class:`~alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage`
class and implementing the relevant methods.

.. _async-uploads-installation:

Installation
------------

Backend Configuration
^^^^^^^^^^^^^^^^^^^^^

The chosen backend class can be set globally in the :setting:`STORAGES <django:STORAGES>` setting:

.. code-block:: python

    STORAGES = {
        "default": {
            "BACKEND": "<your chosen backend class here>"
        },
    }

Alternatively, you can pass a storage class instance to the :attr:`~django:django.db.models.FileField.storage` argument on the model field .

Amazon S3
~~~~~~~~~

To use with Amazon S3 `django-storages with S3 <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#installation>`_
is required. If you installed `alliance_platform_storage` with `-E s3` this will be installed, otherwise run:

.. code-block:: bash

    poetry add django-storages -E s3

To make it the default for fields set the :setting:`STORAGES <django:STORAGES>` setting::

    STORAGES = {
        "default": {
            "BACKEND": "alliance_platform.storage.async_uploads.storage.s3.S3AsyncUploadStorage"
        },
    }

See the `S3 authentication documentation <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#authentication-settings>`_
for what other settings will need to be set.

Azure Blob Storage
~~~~~~~~~~~~~~~~~~

To use with Azure `django-storages with Azure <https://django-storages.readthedocs.io/en/latest/backends/azure.html#installation>`_
is required. If you installed `alliance_platform_storage` with `-E azure` this will be installed, otherwise run:

.. code-block:: bash

    poetry add django-storages -E azure

To make it the default for fields set the :setting:`STORAGES <django:STORAGES>` setting::

    STORAGES = {
        "default": {
            "BACKEND": "alliance_platform.async_uploads.storage.azure.AzureAsyncUploadStorage"
        },
    }

See the `Azure authentication documentation <https://django-storages.readthedocs.io/en/latest/backends/azure.html#authentication-settings>`_
for what other settings will need to be set.

File System
~~~~~~~~~~~

To use with the local filesystem you can use :class:`~alliance_platform.storage.async_uploads.storage.filesystem.FileSystemAsyncUploadStorage`.

To make it the default for fields set the :setting:`STORAGES <django:STORAGES>` setting::

    STORAGES = {
        "default": {
            "BACKEND": "alliance_platform.async_uploads.storage.filesystem.FileSystemAsyncUploadStorage"
        },
    }


.. _register-urls:

Register URLs
^^^^^^^^^^^^^

To facilitate async uploads, some URLs need to be registered. This is crucial for generating upload URLs and handling downloads.
You can register the URLs by calling :meth:`~alliance_platform.storage.async_uploads.registry.AsyncFieldRegistry.get_url_patterns`.

.. code-block:: python

       from alliance_platform.storage.async_uploads.registry import default_async_field_registry

       urlpatterns = [
           # ... other patterns ...
           path("async-uploads/", include(default_async_field_registry.get_url_patterns())),
       ]

.. note::

    If you use multiple registries, you will need to do this for each registry. In most cases the default registry
    is sufficient.

Cleanup command
^^^^^^^^^^^^^^^

Intermediate files are stored in the :class:`alliance_platform.storage.async_uploads.models.AsyncTempFile` table. Periodically clean up these files by running
the :djmanage:`cleanup_async_temp_files` command:

.. code-block:: bash

    python manage.py cleanup_async_temp_files


How it works
------------

The AsyncFile feature works in conjunction with :class:`~alliance_platform.storage.async_uploads.views.GenerateUploadUrlView`. The view generates a URL (e.g., a signed URL when using S3) that the frontend can then use for direct uploads. Each view is tied to a specific registry, which you can specify using ``async_field_registry``
(defaults to :data:`~alliance_platform.storage.async_uploads.registry.default_async_field_registry`). In most cases, a single registry is fine and you don't need to explicitly reference it.

The flow for async file uploads is as follows:

1. When a form is rendered on the frontend (e.g., using :class:`~alliance_platform.storage.async_uploads.forms.AsyncFileField`), it knows the ``async_field_id`` from the registry and the ``generate_upload_url`` endpoint.

2. When an upload occurs, the frontend first hits the ``generate_upload_url`` endpoint, passing the ``async_field_id``, filename, and optionally an ``instance_id`` for updates.

3. :class:`~alliance_platform.storage.async_uploads.views.GenerateUploadUrlView` looks up the registry for the ``async_field_id``, checks permissions, and creates an :class:`~alliance_platform.storage.async_uploads.models.AsyncTempFile` record.

4. The frontend receives the upload URL and uploads the file directly to the storage backend. The key for the :class:`~alliance_platform.storage.async_uploads.models.AsyncTempFile` is stored in the form for submission.

5. Upon form submission, the backend moves the file from its temporary location to its final destination, and cleans up the :class:`~alliance_platform.storage.async_uploads.models.AsyncTempFile` record.

6. If form submission never occurs, for example the user abandons the form after uploading a file, then the file will be retained until
   the :djmanage:`cleanup_async_temp_files` command is run.

Usage
-----

1. Add a :class:`~alliance_platform.storage.async_uploads.models.AsyncFileField`: or :class:`~alliance_platform.storage.async_uploads.models.AsyncImageField` to a model, optionally passing
   the ``storage`` option  if you need to use a different backend from the project :setting:`STORAGES <django:STORAGES>` setting.

   .. code-block:: python

       from alliance_platform.storage.async_uploads.models import AsyncFileField
       from alliance_platform.storage.async_uploads.storage.s3 import S3AsyncUploadStorage

       storage = S3AsyncUploadStorage()

       class MyModel(models.Model):
           file = AsyncFileField()
           # Optionally pass storage
           image = AsyncImageField(storage=storage)

.. _async-uploads-url-config:

2. Form Usage:

   By default, the :class:`~alliance_platform.storage.async_uploads.forms.AsyncFileField` is used to handle uploads
   from Django forms. The default widget is :class:`~alliance_platform.storage.async_uploads.forms.AsyncFileInput`.

3. DRF Integration:

   For Django Rest Framework, use the DRF fields :class:`alliance_platform.storage.drf.serializer.AsyncFileField` or :class:`alliance_platform.storage.drf.serializer.AsyncImageField`.

   You can set this as the default for the corresponding model fields by adding entries to the ``serializer_field_mapping`` on
   a custom ``ModelSerializer`` base class::

        from alliance_platform.storage.drf.serializer import AsyncFileField
        from alliance_platform.storage.drf.serializer import AsyncImageField
        import alliance_platform.storage.async_uploads.models as async_file_fields

        class XenopusFrogAppModelSerializer(ModelSerializer):
            serializer_field_mapping = {
                **ModelSerializer.serializer_field_mapping,
                async_file_fields.AsyncFileField: AsyncFileField,
                async_file_fields.AsyncImageField: AsyncImageField,
            }

Permissions
-----------

Permissions for file operations can be specified using ``perm_create`` and ``perm_update``. If not provided, they default to the value returned by :func:`~alliance_platform.core.auth.resolve_perm_name` for the 'create' and 'update' actions respectively. To disable permission checks, pass ``None``.

.. _async-uploads-cleanup:

Advanced Usage
--------------

For more advanced usage, including custom storage backends, modifying temporary file paths, and handling file overwrites, refer to the API documentation of individual classes and the installation guide.

Note on File Length
-------------------

The key for the file is stored in the database as a CharField with a default max_length of 500. Ensure this is sufficient for your use case, especially when considering temporary file paths and `upload_to` configurations.
You can pass a different ``max_length`` as a kwarg to the field.
