Alliance Platform Storage
=============================================

This package provides classes & fields for working with storage easier.

The :class:`~alliance_platform.storage.fields.async_file.AsyncFileField` and :class:`~alliance_platform.storage.fields.async_file.AsyncImageField`
fields can be used on a model to support uploading direct to the backend (eg. S3) without going through django.
This is done in conjunction with a :class:`~alliance_platform.storage.base.AsyncUploadStorage` class. This package provides
implementations for S3, Azure, and local filesystem, or you can implement your own.

The :class:`~alliance_platform.storage.manifest_storage.ExcludingManifestStaticFilesStorage` class can be used with
django :setting:`STORAGES <django:STORAGES>` to exclude files from being hashed, which is useful when used in conjuction
with a build system that already does hashing.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   settings
   legacy_migration
   usage
   commands
   api

.. include:: ../../ap-core/docs/_sidebar.rst.inc
