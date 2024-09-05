Installation
------------

Install the ``alliance_platform_storage`` package:

.. code-block:: bash

    poetry add alliance_platform_storage

Add ``alliance_platform.storage`` to your ``INSTALLED_APPS``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.storage',
        ...
    ]

Register URLs
~~~~~~~~~~~~~

The core functionality of ``alliance_platform_storage`` is to allow uploading directly to a backend, like S3 or Azure,
and to allow downloading previously uploaded files, while making sure this functionality is only available to
authorised users. To facilitate this, the following URLs need to be registered::

    urlpatterns = [
        path("download-file/", DownloadRedirectView.as_view()),
        path("generate-upload-url/", GenerateUploadUrlView.as_view()),
    ]

You can choose whatever path you like - the above is just an example.

Cleanup Script
~~~~~~~~~~~~~~

The :djmanage:`cleanup_async_temp_files` script should be run periodically to clean up any incomplete uploads. It
can be run as frequently as desired, but once a day is reasonable.

Use with Amazon S3
~~~~~~~~~~~~~~~~~~

To use with Amazon S3 install `django-storages with S3 <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#installation>`_:

.. code-block:: bash

    poetry add django-storages -E s3

To make it the default for fields set the :setting:`STORAGES <django:STORAGES>` setting::

    STORAGES = {
        "default": {
            "BACKEND": "alliance_platform.storage.s3.S3AsyncUploadStorage"
        },
    }

See the `authentication documentation <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#authentication-settings>`_
for what other settings will need to be set.

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

TODO: Fill this out
