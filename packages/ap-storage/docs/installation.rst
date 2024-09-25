Installation
------------

Install the ``alliance_platform_storage`` package:

.. code-block:: bash

    poetry add alliance_platform_storage

If you are using one of the optional backends, you can specify it as an extra:

.. code-block:: bash

    # For Amazon S3
    poetry add alliance_platform_storage -E s3
    # For Azure
    poetry add alliance_platform_storage -E azure

Add ``alliance_platform.storage`` to your ``INSTALLED_APPS``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.storage',
        ...
    ]

.. _register-urls:

Register URLs
~~~~~~~~~~~~~

The core functionality of ``alliance_platform_storage`` is to allow uploading directly to a backend, like S3 or Azure,
and to allow downloading previously uploaded files, while making sure this functionality is only available to
authorised users. To facilitate this, some URLs need to be registered.

The easiest way to do this is to call :meth:`~alliance_platform.storage.registry.AsyncFieldRegistry.get_url_patterns`, which
will return the URLs required for any of the storage classes used::


    from django.urls import include
    from django.urls import path
    from alliance_platform.storage.registry import default_async_field_registry

    urlpatterns = [
        path("async-upload/", include(default_async_field_registry.get_url_patterns())),
    ]

You can choose whatever path you like - the above is just an example.

Cleanup Script
~~~~~~~~~~~~~~

The :djmanage:`cleanup_async_temp_files` script should be run periodically to clean up any incomplete uploads. It
can be run as frequently as desired, but once a day is reasonable.

Use with Amazon S3
~~~~~~~~~~~~~~~~~~

To use with Amazon S3 `django-storages with S3 <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#installation>`_
is required. If you installed `alliance_platform_storage` with `-E s3` this will be installed, otherwise run:

.. code-block:: bash

    poetry add django-storages -E s3

To make it the default for fields set the :setting:`STORAGES <django:STORAGES>` setting::

    STORAGES = {
        "default": {
            "BACKEND": "alliance_platform.storage.s3.S3AsyncUploadStorage"
        },
    }

See the `S3 authentication documentation <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#authentication-settings>`_
for what other settings will need to be set.

Use with Azure Blob Storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To use with Azure `django-storages with Azure <https://django-storages.readthedocs.io/en/latest/backends/azure.html#installation>`_
is required. If you installed `alliance_platform_storage` with `-E azure` this will be installed, otherwise run:

.. code-block:: bash

    poetry add django-storages -E azure

To make it the default for fields set the :setting:`STORAGES <django:STORAGES>` setting::

    STORAGES = {
        "default": {
            "BACKEND": "alliance_platform.storage.azure.AzureAsyncUploadStorage"
        },
    }

See the `Azure authentication documentation <https://django-storages.readthedocs.io/en/latest/backends/azure.html#authentication-settings>`_
for what other settings will need to be set.

Use with File System
~~~~~~~~~~~~~~~~~~~~

To use with the local filesystem you can use :class:`~alliance_platform.storage.filesystem.FileSystemAsyncUploadStorage`.

To make it the default for fields set the :setting:`STORAGES <django:STORAGES>` setting::

    STORAGES = {
        "default": {
            "BACKEND": "alliance_platform.storage.azure.FileSystemAsyncUploadStorage"
        },
    }

Configuration
-------------

.. _storage-configuration:

See above for setting the django :setting:`STORAGES <django:STORAGES>` setting to the relevant storage class.

.. note::

    While not required, it is recommended to install the `CurrentRequestMiddleware <https://github.com/allianceSoftware/django-allianceutils?tab=readme-ov-file#currentrequestmiddleware>`_
    which will give more useful error messages in some cases. To do this add ``allianceutils.middleware.CurrentRequestMiddleware`` to :setting:`MIDDLEWARE <django:MIDDLEWARE>`::

        MIDDLEWARE = (
            ....
            "allianceutils.middleware.CurrentRequestMiddleware",
            ...
        )

See the :doc:`settings` documentation for details about each of the available settings.
