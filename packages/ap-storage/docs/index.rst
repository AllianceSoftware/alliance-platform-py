Alliance Platform Storage
=============================================

This package provides storage classes & fields to make dealing with storage providers easier (e.g. S3, Azure).

The :class:`~alliance_platform.storage.fields.async_file.AsyncFileField` and :class:`~alliance_platform.storage.fields.async_file.AsyncImageField`
fields can be used on a model to support uploading direct to the backend (eg. S3) without going through django.
This is done in conjunction with a :class:`~alliance_platform.storage.base.AsyncUploadStorage` class. This package provides
implementations for S3 & Azure, or you can implement your own.


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
