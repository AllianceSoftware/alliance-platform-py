from alliance_platform.storage.fields.async_file import AsyncFileField
from alliance_platform.storage.fields.async_file import AsyncImageField
from django.db import models
from django.db.models import CASCADE

from test_alliance_platform_storage.storage import DummyStorage


class AsyncFileTestParentModel(models.Model):
    class Meta:
        db_table = "test_alliance_platform_storage_async_file_test_parent_model"


class AsyncFileTestModel(models.Model):
    parent = models.ForeignKey(AsyncFileTestParentModel, on_delete=CASCADE, null=True, related_name="files")
    file1 = AsyncFileField(storage=DummyStorage(), null=True, blank=True)  # type: ignore[abstract] # mypy issue #3115
    image_with_dims = AsyncImageField(  # type: ignore[abstract] # mypy issue #3115
        storage=DummyStorage(),
        null=True,
        blank=True,
        width_field="image_width",
        height_field="image_height",
        suppress_pillow_check=True,
    )
    image_width = models.IntegerField(blank=True, null=True)
    image_height = models.IntegerField(blank=True, null=True)

    image_no_dims = AsyncImageField(storage=DummyStorage(), null=True, blank=True, suppress_pillow_check=True)  # type: ignore[abstract] # mypy issue #3115

    class Meta:
        db_table = "test_alliance_platform_storage_async_file_test_model"
