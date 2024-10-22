API
=============================================


Storage classes
***************

.. autoclass:: alliance_platform.storage.async_uploads.storage.base.AsyncUploadStorage
    :members:

.. autoclass:: alliance_platform.storage.async_uploads.storage.s3.S3AsyncUploadStorage

.. autoclass:: alliance_platform.storage.async_uploads.storage.azure.AzureAsyncUploadStorage

.. autoclass:: alliance_platform.storage.async_uploads.storage.filesystem.FileSystemAsyncUploadStorage

Staticfiles Storage
*******************

.. autoclass:: alliance_platform.storage.staticfiles.storage.ExcludingManifestStaticFilesStorage

Models
******

.. autoclass:: alliance_platform.storage.async_uploads.models.AsyncTempFile

Fields
******

.. autoclass:: alliance_platform.storage.async_uploads.models.AsyncFileMixin

.. autoclass:: alliance_platform.storage.async_uploads.models.AsyncFileField

.. autoclass:: alliance_platform.storage.async_uploads.models.AsyncImageField

.. _storage-serializer-fields:

Serializer Fields
*****************

To automatically map model fields to serializer fields add this to the base ModelSerializer class (this has already
been done in :class:`xenopus_frog_app.base.XenopusFrogAppModelSerializer`):

.. code:: python

    from rest_framework.serializers import ModelSerializer
    from alliance_platform.storage.drf.serializer import AsyncFileField
    from alliance_platform.storage.drf.serializer import AsyncImageField
    import alliance_platform.storage.async_uploads.models as async_file_fields


    class BaseModelSerializer(ModelSerializer):
        serializer_field_mapping = {
            **ModelSerializer.serializer_field_mapping,
            async_file_fields.AsyncFileField: AsyncFileField,
            async_file_fields.AsyncImageField: AsyncImageField,
        }

.. autoclass:: alliance_platform.storage.drf.serializer.AsyncFileField

.. autoclass:: alliance_platform.storage.drf.serializer.AsyncImageField

Forms
*****

.. autoclass:: alliance_platform.storage.async_uploads.forms.AsyncFileField

    .. automethod:: __init__

.. autoclass:: alliance_platform.storage.async_uploads.forms.AsyncFileInput

.. autoclass:: alliance_platform.storage.async_uploads.forms.AsyncFileInputData
    :members:

.. autoclass:: alliance_platform.storage.async_uploads.forms.AsyncImageField

Views
*****

.. autoclass:: alliance_platform.storage.async_uploads.views.GenerateUploadUrlView

.. autoclass:: alliance_platform.storage.async_uploads.views.DownloadRedirectView

.. autoclass:: alliance_platform.storage.async_uploads.views.filesystem.FileSystemAsyncStorageUploadView

.. autoclass:: alliance_platform.storage.async_uploads.views.filesystem.FileSystemAsyncStorageDownloadView

Registry
********

.. autoclass:: alliance_platform.storage.async_uploads.registry.AsyncFieldRegistry
    :members:

.. py:data:: alliance_platform.storage.async_uploads.registry.default_async_field_registry

    The default registry that is used when one is not explicitly specified
