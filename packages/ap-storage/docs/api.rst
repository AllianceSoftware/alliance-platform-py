API
=============================================

.. autoclass:: alliance_platform.storage.base.AsyncUploadStorage
    :members:


Models
******

.. autoclass:: alliance_platform.storage.models.AsyncTempFile

Fields
******

.. autoclass:: alliance_platform.storage.fields.async_file.AsyncFileMixin

.. autoclass:: alliance_platform.storage.fields.async_file.AsyncFileField

.. autoclass:: alliance_platform.storage.fields.async_file.AsyncImageField

.. _storage-serializer-fields:

Serializer Fields
*****************

To automatically map model fields to serializer fields add this to the base ModelSerializer class (this has already
been done in :class:`xenopus_frog_app.base.XenopusFrogAppModelSerializer`):

.. code:: python

    from rest_framework.serializers import ModelSerializer
    from alliance_platform.storage.drf.serializer import AsyncFileField
    from alliance_platform.storage.drf.serializer import AsyncImageField
    import alliance_platform.storage.fields.async_file as async_file_fields


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

.. autoclass:: alliance_platform.storage.fields.async_file.AsyncFileFormField

    .. automethod:: __init__

.. autoclass:: alliance_platform.storage.fields.async_file.AsyncFileInput

.. autoclass:: alliance_platform.storage.fields.async_file.AsyncFileInputData
    :members:

.. autoclass:: alliance_platform.storage.fields.async_file.AsyncImageFormField

Views
*****

.. autoclass:: alliance_platform.storage.views.GenerateUploadUrlView

.. autoclass:: alliance_platform.storage.views.DownloadRedirectView

Registry
********

.. autoclass:: alliance_platform.storage.registry.AsyncFieldRegistry
    :members:

.. py:data:: alliance_platform.storage.registry.default_async_field_registry

    The default registry that is used when one is not explicitly specified
