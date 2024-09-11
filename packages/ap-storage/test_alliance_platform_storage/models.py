from alliance_platform.storage.fields.async_file import AsyncFileField
from alliance_platform.storage.fields.async_file import AsyncImageField
from alliance_platform.storage.registry import AsyncFieldRegistry
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CASCADE

from test_alliance_platform_storage.storage import DummyStorage


class AsyncFileTestParentModel(models.Model):
    class Meta:
        db_table = "test_alliance_platform_storage_async_file_test_parent_model"


storage = DummyStorage()


class AsyncFileTestModel(models.Model):
    parent = models.ForeignKey(AsyncFileTestParentModel, on_delete=CASCADE, null=True, related_name="files")
    file1 = AsyncFileField(storage=storage, null=True, blank=True)
    image_with_dims = AsyncImageField(
        storage=storage,
        null=True,
        blank=True,
        width_field="image_width",
        height_field="image_height",
        suppress_pillow_check=True,
    )
    image_width = models.IntegerField(blank=True, null=True)
    image_height = models.IntegerField(blank=True, null=True)

    image_no_dims = AsyncImageField(storage=storage, null=True, blank=True, suppress_pillow_check=True)

    class Meta:
        db_table = "test_alliance_platform_storage_async_file_test_model"


class AsyncFilePermTestModel(models.Model):
    file_no_perms = AsyncFileField(
        storage=storage, null=True, blank=True, perm_create=None, perm_detail=None, perm_update=None
    )
    file_default_perms = AsyncFileField(storage=storage, null=True, blank=True)
    file_custom_perms = AsyncFileField(
        storage=storage,
        null=True,
        blank=True,
        perm_create="custom_create",
        perm_detail="custom_detail",
        perm_update="custom_update",
    )

    class Meta:
        db_table = "test_alliance_platform_storage_async_file_perm_test_model"


class User(AbstractUser):
    class Meta:
        db_table = "test_alliance_platform_storage_custom_user"


another_registry = AsyncFieldRegistry("another registry")


class AlternateRegistryModel(models.Model):
    file1 = AsyncFileField(storage=storage)
    file2 = AsyncFileField(storage=storage, async_field_registry=another_registry)
