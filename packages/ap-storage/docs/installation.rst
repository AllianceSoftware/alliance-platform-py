Installation
------------

Install the ``alliance_platform_storage`` package:

.. code-block:: bash

    poetry add alliance_platform_storage

If you are using one of the :ref:`optional async upload backends <async-upload-backends>`, you can specify it as an extra:

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

Async Uploads
~~~~~~~~~~~~~

If you are using the :doc:`async_uploads` feature, see the :ref:`async uploads installation instructions<async-uploads-installation>`.

Other settings
~~~~~~~~~~~~~~

.. note::

    While not required, it is recommended to install the `CurrentRequestMiddleware <https://github.com/allianceSoftware/django-allianceutils?tab=readme-ov-file#currentrequestmiddleware>`_
    which will give more useful error messages in some cases. To do this add ``allianceutils.middleware.CurrentRequestMiddleware`` to :setting:`MIDDLEWARE <django:MIDDLEWARE>`::

        MIDDLEWARE = (
            ....
            "allianceutils.middleware.CurrentRequestMiddleware",
            ...
        )

All settings are optional, so you can omit this if the defaults are satisfactory.

In the settings file:

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.storage.settings import AlliancePlatformStorageSettingsType

    class AlliancePlatformSettings(TypedDict):
        CORE: AlliancePlatformCoreSettingsType
        STORAGE: AlliancePlatformStorageSettingsType
        # Any other settings for alliance_platform packages, e.g. FRONTEND

    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "STORAGE": {
            "UPLOAD_URL_EXPIRY": 3600,
            "DOWNLOAD_URL_EXPIRY": 3600,
        },
    }

See the :doc:`settings` documentation for details about each of the available settings.
