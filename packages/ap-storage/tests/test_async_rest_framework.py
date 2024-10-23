import logging
from unittest import mock

import alliance_platform.storage.async_uploads.models as async_file_fields
from alliance_platform.storage.async_uploads.models import AsyncTempFile
from alliance_platform.storage.async_uploads.models import default_max_length as async_file_max_length
from alliance_platform.storage.async_uploads.rest_framework import AsyncFileField
from alliance_platform.storage.async_uploads.rest_framework import AsyncImageField
from django.test import TestCase
from rest_framework import serializers
from test_alliance_platform_storage.models import AsyncFileTestModel
from test_alliance_platform_storage.models import AsyncFileTestParentModel


class AsyncFileTestModelSerializer(serializers.ModelSerializer):
    serializer_field_mapping = {
        **serializers.ModelSerializer.serializer_field_mapping,
        async_file_fields.AsyncFileField: AsyncFileField,
        async_file_fields.AsyncImageField: AsyncImageField,
    }

    class Meta:
        fields = ("file1", "image_with_dims")
        model = AsyncFileTestModel


class AsyncFileTestModelParentSerializer(serializers.ModelSerializer):
    files = AsyncFileTestModelSerializer(many=True, required=False)

    class Meta:
        fields = ("files",)
        model = AsyncFileTestParentModel


class SerializerAsyncFileTestCase(TestCase):
    def test_file_field(self):
        pdf = AsyncTempFile.create_for_field(AsyncFileTestModel._meta.get_field("file1"), "test.pdf")
        image = AsyncTempFile.create_for_field(
            AsyncFileTestModel._meta.get_field("image_with_dims"), "test.png"
        )
        serializer = AsyncFileTestModelSerializer(
            data=dict(
                file1={"key": pdf.key, "name": pdf.original_filename},
                image_with_dims={
                    "key": image.key,
                    "name": image.original_filename,
                    "width": 16,
                    "height": 24,
                },
            )
        )
        serializer.is_valid(raise_exception=True)
        with mock.patch("test_alliance_platform_storage.storage.DummyStorage._open") as mock_method:
            instance = serializer.save()

            mock_method.assert_not_called()

            self.assertEqual(instance.file1, "test.pdf")
            self.assertEqual(instance.image_with_dims, "test.png")
            self.assertEqual(instance.image_width, 16)
            self.assertEqual(instance.image_height, 24)

    def test_reject_bad_input(self):
        # Can't change the key on a field
        serializer = AsyncFileTestModelSerializer(data={"image_with_dims": "whatever.png"})
        self.assertFalse(serializer.is_valid())
        self.assertRegex(serializer.errors["image_with_dims"][0], "Bad input for file field")

        with self.assertLogs(logging.getLogger("alliance_platform.storage")):
            # Key isn't prefixed as a temporary path so must be rejected
            serializer = AsyncFileTestModelSerializer(
                data={"image_with_dims": {"key": "/storage/test.png", "name": "test.png"}}
            )
            self.assertFalse(serializer.is_valid())
            self.assertRegex(serializer.errors["image_with_dims"][0], "Invalid upload received")

        # Check max_length is validated
        tf = AsyncTempFile.create_for_field(
            AsyncFileTestModel._meta.get_field("image_with_dims"), "a" * (async_file_max_length + 1)
        )
        serializer = AsyncFileTestModelSerializer(
            data={"image_with_dims": {"key": tf.key, "name": tf.original_filename}}
        )
        self.assertFalse(serializer.is_valid())

        tf = AsyncTempFile.create_for_field(
            AsyncFileTestModel._meta.get_field("image_with_dims"), "a" * async_file_max_length
        )
        serializer = AsyncFileTestModelSerializer(
            data={"image_with_dims": {"key": tf.key, "name": tf.original_filename}}
        )
        self.assertTrue(serializer.is_valid())

        tf = AsyncTempFile.create_for_field(AsyncFileTestModel._meta.get_field("image_with_dims"), "test.png")
        tm = AsyncFileTestModel.objects.create(
            image_with_dims=async_file_fields.AsyncFileInputData(
                key=tf.key, name=tf.original_filename, width=32, height=32
            )
        )
        self.assertEqual(tm.image_with_dims.name, "test.png")
        self.assertEqual(tm.image_width, 32)
        self.assertEqual(tm.image_height, 32)

        # Key matches existing record, should be fine
        serializer = AsyncFileTestModelSerializer(
            data={"image_with_dims": {"key": "test.png", "name": "test.png"}}, instance=tm
        )
        self.assertTrue(serializer.is_valid())

        with self.assertLogs(logging.getLogger("alliance_platform.storage")):
            # Changing the key on existing item isn't accepted (unless it's a temp path)
            serializer = AsyncFileTestModelSerializer(
                data={"image_with_dims": {"key": "test2.png", "name": "test.png"}}, instance=tm
            )
            self.assertFalse(serializer.is_valid())
            self.assertRegex(serializer.errors["image_with_dims"][0], "Invalid upload received")

        tf = AsyncTempFile.create_for_field(
            AsyncFileTestModel._meta.get_field("image_with_dims"), "test2.png"
        )
        serializer = AsyncFileTestModelSerializer(
            data={"image_with_dims": {"key": tf.key, "name": "test2.png", "width": 16, "height": 16}},
            instance=tm,
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        tm = AsyncFileTestModel.objects.get(pk=tm.pk)

        self.assertEqual(tm.image_with_dims.name, "test2.png")
        self.assertEqual(tm.image_width, 16)
        self.assertEqual(tm.image_height, 16)

    def test_nested_serializer_behavior(self):
        parent = AsyncFileTestParentModel.objects.create()
        temp_file = AsyncTempFile.create_for_field(
            AsyncFileTestModel._meta.get_field("image_with_dims"), "test.png"
        )
        test_model = AsyncFileTestModel.objects.create(
            parent=parent,
            image_with_dims=async_file_fields.AsyncFileInputData(
                key=temp_file.key, name=temp_file.original_filename, width=32, height=32
            ),
        )

        # We have a workaround for nested serializers to track the instance, which is otherwise unavailable in async_uploads.rest_framework.
        # This test covers that patch - if this fails in the future it likely indicates async_uploads.rest_framework has better
        # handling of nested serializers and we can drop our patch.
        with self.assertLogs(logging.getLogger("alliance_platform.storage")):
            data = AsyncFileTestModelSerializer(instance=test_model).data
            nesting_serializer = AsyncFileTestModelParentSerializer(
                data={"files": [data]},
                instance=parent,
            )
            self.assertFalse(nesting_serializer.is_valid())

        # emulates FE payload where id would be included
        data["id"] = test_model.id

        # test that when frontend submits a nested request with unchanged data, it succeeds
        nesting_serializer = AsyncFileTestModelParentSerializer(
            data={"files": [data]},
            instance=parent,
        )
        self.assertTrue(nesting_serializer.is_valid())

        # test that changing the file also wont raise a validation error on changed key
        new_temp_file = AsyncTempFile.create_for_field(
            AsyncFileTestModel._meta.get_field("image_with_dims"), "test2.png"
        )
        data["image_with_dims"] = {"key": new_temp_file.key, "name": "test2.png", "width": 16, "height": 16}
        nesting_serializer = AsyncFileTestModelParentSerializer(
            data={"files": [data]},
            instance=parent,
        )
        self.assertTrue(nesting_serializer.is_valid())
