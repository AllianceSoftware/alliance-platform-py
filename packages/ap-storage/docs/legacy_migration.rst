Legacy Migration
----------------

These instructions can be used to migrate a project using the legacy ``common_storage`` package to ``alliance_platform_storage``.

Install the ``alliance_platform_storage`` package as per the :doc:`installation instructions <installation>`.

.. note::

    If this is an older project that is not using the published ``alliance_platform`` packages at all you will need to
    add the following to ``settings/base.py`` (at minimum) if no ``ALLIANCE_PLATFORM`` setting already exists::

        ALLIANCE_PLATFORM = {
            "CORE": {"PROJECT_DIR": PROJECT_DIR},
        }

Follow these steps:

* For the widget to continue working you will need to copy the ``common_storage/templates/widgets/async_file_input.html`` file
  to ``<app>/templates/alliance_platform/storage/widgets/async_file_input.html``. ``<app>`` can be any of the project
  specific apps (in the base template ``xenopus_frog_app`` for example, or ``django_site``).
* Delete the ``common_storage`` app entirely from ``django-root``, and remove it from ``INSTALLED_APPS``.
* Remove ``common_storage.test_common_storage`` from ``TEST_APPS`` in ``settings/base.py``.
* Search and replace ``common_storage`` with ``alliance_platform.storage``. This should update all existing imports
  or setting references (e.g. ``DEFAULT_FILE_STORAGE``)
* In ``urls.py`` remove the paths for ``DownloadRedirectView`` and ``GenerateUploadView``, and add the following instead
  (if not already done as part of installation)::

    # You can change the path to whatever you like, or add the patterns to the top level
    path("async-file/", include(default_async_field_registry.get_url_patterns())),

When you migrate, if the ``common_storage_async_temp_file`` table exists its data will be copied into the corresponding
table in ``alliance_platform.storage``.

.. warning::

    Before doing this upgrade, check that the ``AsyncTempFile`` table has the following fields, otherwise the
    migration will break. If any of these fields don't exist you will need to first upgrade to the latest version of
    `common_storage <https://gitlab.internal.alliancesoftware.com.au/alliance/template-django/-/tree/10d5f3466ad5a2a7304f5db4c0aaf17d054593ec/django-root/common_storage>`_.

   * created_at
   * original_filename
   * key
   * field_name
   * content_type_id
   * error
   * moved_to_location


Notable differences
===================

The only potential breaking change in async uploads between the most recent version of `common_storage <https://gitlab.internal.alliancesoftware.com.au/alliance/template-django/-/tree/10d5f3466ad5a2a7304f5db4c0aaf17d054593ec/django-root/common_storage>`_
and the initial published version of ``alliance_platform_storage`` is the addition of the ``field_id`` argument to
:meth:`~alliance_platform.storage.base.AsyncUploadStorage.generate_upload_url` and
:meth:`~alliance_platform.storage.base.AsyncUploadStorage.generate_download_url`. However, this will only matter if you are
calling these functions directly, or have extended an ``AsyncUploadStorage`` class and overridden these methods. If so,
you will just need to update the signature to accept the ``field_id`` argument.

ManifestStaticFilesExcludeWebpackStorage
========================================

The other change is the removal of the ``ManifestStaticFilesExcludeWebpackStorage`` class. Instead, you can now use
:class:`~alliance_platform.storage.staticfiles.storage.ExcludingManifestStaticFilesStorage`. Its usage would be something
like::

    STORAGES = {
        "staticfiles": {
            "BACKEND": "alliance_platform.storage.staticfiles.storage.ExcludingManifestStaticFilesStorage",
            # Adjust this based on the specific setting name or build directory in your project
            "OPTIONS": {"exclude_patterns": [f"{settings.FRONTEND_PRODUCTION_DIR}/*"]},
        }
    }
