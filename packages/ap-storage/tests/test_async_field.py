from hashlib import shake_256
import json
import logging
import os
from typing import Literal
from typing import cast
from unittest import mock
from unittest.mock import patch
from urllib.parse import urlencode

from alliance_platform.storage.async_uploads.forms import AsyncFileInput
from alliance_platform.storage.async_uploads.models import AsyncFileField
from alliance_platform.storage.async_uploads.models import AsyncFileInputData
from alliance_platform.storage.async_uploads.models import AsyncTempFile
from alliance_platform.storage.async_uploads.models import default_max_length as async_file_max_length
from alliance_platform.storage.async_uploads.registry import default_async_field_registry
from django.core.exceptions import SuspiciousFileOperation
from django.core.exceptions import ValidationError
from django.core.files import File
from django.forms import ModelForm
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from test_alliance_platform_storage.models import AlternateRegistryModel
from test_alliance_platform_storage.models import AsyncFilePermTestModel
from test_alliance_platform_storage.models import AsyncFileTestChildModel
from test_alliance_platform_storage.models import AsyncFileTestModel
from test_alliance_platform_storage.models import User
from test_alliance_platform_storage.models import another_registry
from test_alliance_platform_storage.storage import DummyStorage

TEST_IMAGE_PATH = os.path.join(
    os.path.dirname(__file__) + "/../test_alliance_platform_storage/files/test.png"
)
TEST_IMAGE_64_64_PATH = os.path.join(
    os.path.dirname(__file__) + "/../test_alliance_platform_storage/files/test-64x64.png"
)

DUMMY_STORAGES_SETTING = {
    "default": {
        "BACKEND": "test_alliance_platform_storage.storage.DummyStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


class AsyncFileMixinTestCase(TestCase):
    MODELS_TO_TEST = [AsyncFileTestModel, AsyncFileTestChildModel]

    def test_validate_storage_class(self):
        with override_settings(
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            }
        ):
            with self.assertRaisesRegex(ValueError, "file storage class must extend AsyncUploadStorage"):
                AsyncFileField()
        with override_settings(STORAGES=DUMMY_STORAGES_SETTING):
            AsyncFileField()

    def test_registry(self):
        field1 = AlternateRegistryModel._meta.get_field("file1")
        field2 = AlternateRegistryModel._meta.get_field("file2")
        self.assertEqual(field1.async_field_registry, default_async_field_registry)
        self.assertEqual(
            default_async_field_registry.fields_by_id[default_async_field_registry.generate_id(field1)],
            field1,
        )
        self.assertEqual(field2.async_field_registry, another_registry)
        self.assertEqual(another_registry.fields_by_id[another_registry.generate_id(field2)], field2)

    def test_image_field_dimensions(self):
        for async_model_to_test in self.MODELS_TO_TEST:
            with self.subTest(async_model_to_test.__name__):
                with mock.patch("test_alliance_platform_storage.storage.DummyStorage._open") as mock_method:
                    tf = AsyncTempFile.create_for_field(
                        async_model_to_test._meta.get_field("image_with_dims"), "example.png"
                    )
                    tm = async_model_to_test.objects.create(
                        image_with_dims=AsyncFileInputData(
                            key=tf.key, name=tf.original_filename, width=32, height=32
                        )
                    )
                    self.assertEqual(tm.image_with_dims, "example.png")
                    self.assertEqual(tm.image_width, 32)
                    self.assertEqual(tm.image_height, 32)

                    # If width & height are set using AsyncFileInputData then storage should not have to open the file
                    mock_method.assert_not_called()

                    mock_method.return_value = File(open(TEST_IMAGE_PATH, "rb"))

                    # This should result in storage opening the file and reading dimensions from there
                    tm.image_with_dims = "test.png"
                    tm.save()

                    self.assertEqual(tm.image_with_dims, "test.png")
                    self.assertEqual(tm.image_width, 16)
                    self.assertEqual(tm.image_height, 16)

                    mock_method.assert_called_once_with("test.png", "rb")
                    mock_method.mock_reset()

                with mock.patch("test_alliance_platform_storage.storage.DummyStorage._open") as mock_method:
                    mock_method.return_value = File(open(TEST_IMAGE_PATH, "rb"))
                    # Not passing dimensions should result in file being read for it
                    tf = AsyncTempFile.create_for_field(
                        async_model_to_test._meta.get_field("image_with_dims"), "example.png"
                    )
                    tm = async_model_to_test.objects.create(
                        image_with_dims=AsyncFileInputData(key=tf.key, name="example.png")
                    )
                    self.assertEqual(tm.image_width, 16)
                    self.assertEqual(tm.image_height, 16)

                    mock_method.assert_called_once_with(tf.key, "rb")

    def test_image_field_dimensions_recalculate(self):
        # only test for parent model - we know that child model doesn't work for dimension recalculation.
        # this is because Django runs size retrieval at initialisation using a post_init signal. signals
        # don't activate for child models, and since the post_init signal is connected in the field's
        # internal contribute_to_class function, the signal is only attached to the parent model
        with mock.patch("test_alliance_platform_storage.storage.DummyStorage._open") as mock_method:
            tf = AsyncTempFile.create_for_field(
                AsyncFileTestModel._meta.get_field("image_with_dims"), "example.png"
            )
            tm = AsyncFileTestModel.objects.create(
                image_with_dims=AsyncFileInputData(key=tf.key, name=tf.original_filename, width=32, height=32)
            )
            self.assertEqual(tm.image_with_dims, "example.png")
            self.assertEqual(tm.image_width, 32)
            self.assertEqual(tm.image_height, 32)

            # Retrieving from database shouldn't trigger a calculation of dimensions either
            tm = AsyncFileTestModel.objects.get(pk=tm.pk)

            # If width & height are set using AsyncFileInputData then storage should not have to open the file
            mock_method.assert_not_called()

            mock_method.return_value = File(open(TEST_IMAGE_PATH, "rb"))
            tm.image_with_dims = "test.png"
            self.assertEqual(tm.image_width, 16)
            self.assertEqual(tm.image_height, 16)

            # refresh_from_db will trigger login in AsyncImageDescriptor
            mock_method.return_value = File(open(TEST_IMAGE_64_64_PATH, "rb"))
            # Assign same name but different underlying file; should recalculate width
            tm.image_with_dims = "test.png"

            self.assertEqual(tm.image_with_dims, "test.png")
            self.assertEqual(tm.image_width, 64)
            self.assertEqual(tm.image_height, 64)

            # Assigning after creation should trigger dimensions lookup
            mock_method.return_value = File(open(TEST_IMAGE_64_64_PATH, "rb"))
            tm = AsyncFileTestModel()
            tm.image_with_dims = "test.png"
            self.assertEqual(tm.image_with_dims, "test.png")
            self.assertEqual(tm.image_width, 64)
            self.assertEqual(tm.image_height, 64)

            # Using __init__ should trigger dimensions lookup
            mock_method.return_value = File(open(TEST_IMAGE_64_64_PATH, "rb"))
            tm = AsyncFileTestModel(image_with_dims="test.png")
            self.assertEqual(tm.image_with_dims, "test.png")
            self.assertEqual(tm.image_width, 64)
            self.assertEqual(tm.image_height, 64)

            # Using AsyncFileInputData with NO dimensions should trigger lookup
            mock_method.return_value = File(open(TEST_IMAGE_64_64_PATH, "rb"))
            tf = AsyncTempFile.create_for_field(
                AsyncFileTestModel._meta.get_field("image_with_dims"), "test.png"
            )
            tm = AsyncFileTestModel(image_with_dims=AsyncFileInputData(key=tf.key, name=tf.original_filename))
            self.assertEqual(tm.image_width, 64)
            self.assertEqual(tm.image_height, 64)

            # Using AsyncFileInputData WITH dimensions should NOT trigger lookup
            mock_method.reset_mock()
            tf = AsyncTempFile.create_for_field(
                AsyncFileTestModel._meta.get_field("image_with_dims"), "test.png"
            )
            tm = AsyncFileTestModel(
                image_with_dims=AsyncFileInputData(key=tf.key, name=tf.original_filename, width=16, height=16)
            )
            self.assertEqual(tm.image_width, 16)
            self.assertEqual(tm.image_height, 16)
            mock_method.assert_not_called()

    def test_image_field_dimensions_refresh_from_db(self):
        for async_model_to_test in self.MODELS_TO_TEST:
            with self.subTest(async_model_to_test.__name__):
                with mock.patch("test_alliance_platform_storage.storage.DummyStorage._open") as mock_method:
                    tf = AsyncTempFile.create_for_field(
                        async_model_to_test._meta.get_field("image_with_dims"), "example.png"
                    )
                    tm = async_model_to_test.objects.create(
                        image_with_dims=AsyncFileInputData(
                            key=tf.key, name=tf.original_filename, width=32, height=32
                        )
                    )
                    self.assertEqual(tm.image_with_dims, "example.png")
                    self.assertEqual(tm.image_width, 32)
                    self.assertEqual(tm.image_height, 32)

                    # If width & height are set using AsyncFileInputData then storage should not have to open the file
                    mock_method.assert_not_called()

                    tm2 = async_model_to_test.objects.get(pk=tm.pk)

                    mock_method.return_value = File(open(TEST_IMAGE_PATH, "rb"))
                    tm2.image_with_dims = "test.png"
                    tm2.save()
                    mock_method.assert_called_once_with("test.png", "rb")
                    mock_method.reset_mock()

                    # refresh_from_db will trigger logic in AsyncImageDescriptor that results in
                    # update_dimensions_being called. Technically this isn't necessary; if the
                    # record was retrieved direct from database instead of refresh_from_db it
                    # would not do this. Unfortunately we don't know about refresh_from_db in
                    # the field and so it just looks like the value has changed.
                    mock_method.return_value = File(open(TEST_IMAGE_PATH, "rb"))
                    tm.refresh_from_db()
                    mock_method.assert_called_once_with("test.png", "rb")

                    self.assertEqual(tm.image_with_dims, "test.png")
                    self.assertEqual(tm.image_width, 16)
                    self.assertEqual(tm.image_height, 16)

    def test_image_field_no_dimensions(self):
        with mock.patch("test_alliance_platform_storage.storage.DummyStorage._open") as mock_method:
            for async_model_to_test in self.MODELS_TO_TEST:
                with self.subTest(async_model_to_test.__name__):
                    tf = AsyncTempFile.create_for_field(
                        async_model_to_test._meta.get_field("image_no_dims"), "test.png"
                    )
                    tm = async_model_to_test.objects.create(
                        image_no_dims=AsyncFileInputData(key=tf.key, name=tf.original_filename)
                    )
                    self.assertEqual(tm.image_no_dims.name, "test.png")
                    mock_method.assert_not_called()

    def test_field_url(self):
        for async_model_to_test in self.MODELS_TO_TEST:
            with self.subTest(async_model_to_test.__name__):
                file1 = AsyncTempFile.create_for_field(
                    async_model_to_test._meta.get_field("file1"), "test.png"
                )
                file2 = AsyncTempFile.create_for_field(
                    async_model_to_test._meta.get_field("image_no_dims"), "example.png"
                )
                tm = async_model_to_test.objects.create(
                    file1=file1.key,
                    image_no_dims=AsyncFileInputData(key=file2.key, name=file2.original_filename),
                )
                field = async_model_to_test._meta.get_field("file1")
                registry = field.async_field_registry
                self.assertEqual(
                    tm.file1.url,
                    reverse(registry.attached_download_view)
                    + f"?field_id={registry.generate_id(field)}&instance_id={tm.pk}&_={shake_256(tm.file1.name.encode()).hexdigest(8)}",
                )
                field = async_model_to_test._meta.get_field("image_no_dims")
                registry = field.async_field_registry
                self.assertEqual(
                    tm.image_no_dims.url,
                    reverse(field.async_field_registry.attached_download_view)
                    + f"?field_id={registry.generate_id(field)}&instance_id={tm.pk}&_={shake_256(tm.image_no_dims.name.encode()).hexdigest(8)}",
                )

    def test_move_file(self):
        for async_model_to_test in self.MODELS_TO_TEST:
            with self.subTest(async_model_to_test.__name__):
                tf = AsyncTempFile.create_for_field(async_model_to_test._meta.get_field("file1"), "test.pdf")
                file = AsyncFileInputData(key=tf.key, name=tf.original_filename)
                tm = async_model_to_test.objects.create(file1=file)
                self.assertEqual(tm.file1.name, "test.pdf")

                # No error; key is same
                tm.file1 = AsyncFileInputData(key="test.pdf", name="test.pdf")
                tm.save()

                # Error; can't change key using AsyncFileInputData
                with self.assertRaisesRegex(ValidationError, "Invalid upload"):
                    with self.assertLogs(logging.getLogger("alliance_platform.storage")):
                        tm.file1 = AsyncFileInputData(key="test2.pdf", name="test.pdf")
                        tm.save()

                # No problem setting a new temp file location however
                tf = AsyncTempFile.create_for_field(async_model_to_test._meta.get_field("file1"), "test2.pdf")
                tm.file1 = AsyncFileInputData(key=tf.key, name=tf.original_filename)
                tm.save()
                self.assertEqual(tm.file1.name, "test2.pdf")

    def test_move_image_file(self):
        for async_model_to_test in self.MODELS_TO_TEST:
            with self.subTest(async_model_to_test.__name__):
                with mock.patch("test_alliance_platform_storage.storage.DummyStorage._open") as mock_method:
                    # On creation the temp file will be moved to the final location. As part
                    # of this dimensions should _not_ be calculated as they were passed in.
                    tf = AsyncTempFile.create_for_field(
                        async_model_to_test._meta.get_field("image_with_dims"), "test.png"
                    )
                    tm = async_model_to_test.objects.create(
                        image_with_dims=AsyncFileInputData(
                            key=tf.key, name=tf.original_filename, width=32, height=32
                        )
                    )
                    self.assertEqual(tm.image_with_dims.name, "test.png")
                    self.assertEqual(tm.image_width, 32)
                    self.assertEqual(tm.image_height, 32)

                    # If width & height are set using AsyncFileInputData then storage should not have to open the file
                    mock_method.assert_not_called()

                    # If temp file is created without passing the width/height then we
                    # do expect the dimensions to be calculated, but only once
                    tf = AsyncTempFile.create_for_field(
                        async_model_to_test._meta.get_field("image_with_dims"), "test.png"
                    )
                    mock_method.return_value = File(open(TEST_IMAGE_PATH, "rb"))
                    tm = async_model_to_test.objects.create(
                        image_with_dims=AsyncFileInputData(key=tf.key, name=tf.original_filename)
                    )

                    self.assertEqual(tm.image_with_dims, "test.png")
                    self.assertEqual(tm.image_width, 16)
                    self.assertEqual(tm.image_height, 16)

                    mock_method.assert_called_once_with(tf.key, "rb")
                    mock_method.mock_reset()

    def test_move_multiple_files(self):
        for i, async_model_to_test in enumerate(self.MODELS_TO_TEST):
            test_count = i + 1
            if async_model_to_test == AsyncFileTestModel:
                # 2 for transaction (savepoint + release), 1 for initial create, 1 for save on instance after files moved, 1 to select temp files, 1 to update temp files
                expected_queries = 6
            else:
                # 2 additional queries - 1 for create in child table, one for update in child table
                expected_queries = 8
            with self.subTest(async_model_to_test.__name__):
                # On creation the temp file will be moved to the final location. As part
                # of this dimensions should _not_ be calculated as they were passed in.
                image_with_dims = AsyncTempFile.create_for_field(
                    async_model_to_test._meta.get_field("image_with_dims"), "test.png"
                )
                image_no_dims = AsyncTempFile.create_for_field(
                    async_model_to_test._meta.get_field("image_no_dims"), "test2.png"
                )
                file1 = AsyncTempFile.create_for_field(
                    async_model_to_test._meta.get_field("file1"), "test.pdf"
                )
                with self.assertNumQueries(expected_queries):
                    tm = async_model_to_test.objects.create(
                        file1=AsyncFileInputData(key=file1.key, name=file1.original_filename),
                        image_no_dims=AsyncFileInputData(
                            key=image_no_dims.key, name=image_no_dims.original_filename
                        ),
                        image_with_dims=AsyncFileInputData(
                            key=image_with_dims.key,
                            name=image_with_dims.original_filename,
                            width=32,
                            height=32,
                        ),
                    )
                self.assertEqual(tm.image_with_dims.name, "test.png")
                self.assertEqual(tm.image_width, 32)
                self.assertEqual(tm.image_height, 32)

                self.assertEqual(tm.image_no_dims.name, "test2.png")
                self.assertEqual(tm.file1.name, "test.pdf")

                self.assertEqual(AsyncTempFile.objects.filter(moved_to_location="").count(), 0)
                self.assertEqual(
                    AsyncTempFile.objects.filter(moved_to_location__startswith="test").count(), 3 * test_count
                )

    def test_move_multiple_files_errors(self):
        for i, async_model_to_test in enumerate(self.MODELS_TO_TEST):
            test_count = i + 1
            if async_model_to_test == AsyncFileTestModel:
                # 2 for transaction (savepoint & release savepoint)
                # 1 for initial create, 1 for save on instance after files moved, 1 to select temp files, 1 to delete temp files and
                # 1 to save the error on the file1 AsyncTempFile
                expected_queries = 7
            else:
                # 2 additional queries - 1 for create in child table, one for update in child table
                expected_queries = 9
            with self.subTest(async_model_to_test.__name__):
                # On creation the temp file will be moved to the final location. As part
                # of this dimensions should _not_ be calculated as they were passed in.
                image_with_dims = AsyncTempFile.create_for_field(
                    async_model_to_test._meta.get_field("image_with_dims"), "test.png"
                )
                image_no_dims = AsyncTempFile.create_for_field(
                    async_model_to_test._meta.get_field("image_no_dims"), "test2.png"
                )
                file1 = AsyncTempFile.create_for_field(
                    async_model_to_test._meta.get_field("file1"), "test.pdf"
                )

                def fail_on_file1(self, from_key, to_key):
                    if to_key == "test.pdf":
                        raise ValueError("Cannot move")

                with mock.patch(
                    "test_alliance_platform_storage.storage.DummyStorage.move_file", new=fail_on_file1
                ):
                    with self.assertNumQueries(expected_queries):
                        with self.assertLogs(logging.getLogger("alliance_platform.storage")):
                            tm = async_model_to_test.objects.create(
                                file1=AsyncFileInputData(key=file1.key, name=file1.original_filename),
                                image_no_dims=AsyncFileInputData(
                                    key=image_no_dims.key, name=image_no_dims.original_filename
                                ),
                                image_with_dims=AsyncFileInputData(
                                    key=image_with_dims.key,
                                    name=image_with_dims.original_filename,
                                    width=32,
                                    height=32,
                                ),
                            )
                self.assertEqual(tm.image_with_dims.name, "test.png")
                self.assertEqual(tm.image_width, 32)
                self.assertEqual(tm.image_height, 32)

                self.assertEqual(tm.image_no_dims.name, "test2.png")
                self.assertEqual(tm.file1.name, file1.key)

                file1.refresh_from_db()

                self.assertEqual(AsyncTempFile.objects.filter(error__isnull=False).count(), 1 * test_count)
                self.assertEqual(
                    AsyncTempFile.objects.filter(moved_to_location__startswith="test").count(), 2 * test_count
                )
                self.assertRegex(file1.error, "Cannot move")


class AsyncFileFormTestCase(TestCase):
    def test_model_form_image(self):
        class AsyncFileTestModelForm(ModelForm):
            class Meta:
                model = AsyncFileTestModel
                fields = ["image_with_dims"]

        tf = AsyncTempFile.create_for_field(AsyncFileTestModel._meta.get_field("image_with_dims"), "test.png")
        key = tf.key
        form = AsyncFileTestModelForm(
            data={
                "image_with_dims": json.dumps(
                    {
                        "key": key,
                        "name": "test.png",
                        "width": 224,
                        "height": 550,
                    }
                )
            }
        )
        form.save()
        self.assertEqual(AsyncFileTestModel.objects.count(), 1)
        tm = AsyncFileTestModel.objects.first()
        self.assertEqual(tm.image_with_dims, tf.original_filename)
        self.assertEqual(tm.image_width, 224)
        self.assertEqual(tm.image_height, 550)

    def test_reject_bad_input(self):
        class AsyncFileTestModelForm(ModelForm):
            class Meta:
                model = AsyncFileTestModel
                fields = ["image_no_dims"]

        # Can't change the key on a field
        form = AsyncFileTestModelForm(data={"image_no_dims": "whatever.png"})
        self.assertFalse(form.is_valid())
        self.assertRegex(form.errors["image_no_dims"][0], "Bad input for file field")

        with self.assertLogs(logging.getLogger("alliance_platform.storage")):
            # Key isn't prefixed as a temporary path so must be rejected
            form = AsyncFileTestModelForm(
                data={"image_no_dims": json.dumps({"key": "/storage/test.png", "name": "test.png"})}
            )
            self.assertFalse(form.is_valid())
            self.assertRegex(form.errors["image_no_dims"][0], "Invalid upload received")

    def test_file_input(self):
        tm = AsyncFileTestModel.objects.create(image_no_dims="/storage/test.png")
        input = AsyncFileInput()
        field = tm._meta.get_field("image_no_dims")
        self.assertEqual(
            input.format_value(tm.image_no_dims),
            json.dumps(
                {
                    "key": "/storage/test.png",
                    "name": "test.png",
                    "url": f"/download-file/?field_id={field.async_field_registry.generate_id(field)}&instance_id={tm.pk}&_={shake_256(tm.image_no_dims.name.encode()).hexdigest(8)}",
                }
            ),
        )

    def test_file_input_max_len(self):
        class AsyncFileTestModelForm(ModelForm):
            class Meta:
                model = AsyncFileTestModel
                fields = ["image_no_dims"]

        name = "a" * (async_file_max_length + 1)
        key = f"{DummyStorage.temporary_key_prefix}/{name}"
        form = AsyncFileTestModelForm({"image_no_dims": json.dumps({"key": key, "name": name})})
        self.assertFalse(form.is_valid())
        self.assertRegex(
            form.errors["image_no_dims"][0],
            f"Ensure this value has at most {async_file_max_length} characters",
        )
        name = "a" * async_file_max_length
        key = f"{DummyStorage.temporary_key_prefix}/{name}"
        form = AsyncFileTestModelForm({"image_no_dims": json.dumps({"key": key, "name": name})})
        self.assertFalse(form.errors)

    def test_generate_temporary_path(self):
        storage = DummyStorage()
        temp_prefix_length = len("async-temp-files/2021/03/03/fVy5cSVBQpOb-")
        # Just enough to fit the extension
        length = temp_prefix_length + 4
        p = storage.generate_temporary_path("test.png", max_length=length)
        self.assertEqual(len(p), length)
        self.assertTrue(p.endswith("-.png"))

        # Can't fit the extension, error
        with self.assertRaises(SuspiciousFileOperation):
            storage.generate_temporary_path("test.png", max_length=length - 1)

        self.assertTrue(storage.generate_temporary_path("test.png").endswith("-test.png"))


class GenerateUploadUrlViewTestCase(TestCase):
    def _get_url(self, instance: AsyncFileTestModel | None = None, filename="abc.jpg"):
        field_id = default_async_field_registry.generate_id(AsyncFileTestModel._meta.get_field("file1"))
        query_params = dict(field_id=field_id, filename=filename)
        if instance:
            query_params["instanceId"] = instance.pk
        return f"{reverse(default_async_field_registry.attached_view)}?{urlencode(query_params)}"

    def _get_perm_url(
        self,
        field_name: Literal["file_no_perms", "file_custom_perms", "file_default_perms"],
        instance: AsyncFilePermTestModel | None = None,
        filename="abc.jpg",
    ):
        """Return a URL for the AsyncFilePermTestModel"""
        field_id = default_async_field_registry.generate_id(
            cast(AsyncFileField, AsyncFilePermTestModel._meta.get_field(field_name))
        )
        query_params = dict(fieldId=field_id, filename=filename)
        if instance:
            query_params["instanceId"] = instance.pk
        return f"{reverse(default_async_field_registry.attached_view)}?{urlencode(query_params)}"

    def test_validation(self):
        tests = [
            ({}, {"filename": ["This field is required."], "fieldId": ["This field is required."]}),
            ({"filename": "abc.jpg", "field_id": "invalid"}, {"fieldId": ["Unknown fieldId"]}),
        ]
        for params, errors in tests:
            with self.subTest(params=params):
                url = f"{reverse(default_async_field_registry.attached_view)}?{urlencode(params)}"
                response = self.client.get(url)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), errors)

    def test_no_permission_required(self):
        response = self.client.get(self._get_perm_url("file_no_perms"))
        self.assertEqual(response.status_code, 200)

    def test_perm_denied(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=False):
            user = User.objects.create(username="test")
            self.client.force_login(user)
            response = self.client.get(self._get_perm_url("file_custom_perms"))
            self.assertEqual(response.status_code, 403)

    def test_custom_perm_create(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True) as mock_has_perm:
            user = User.objects.create(username="test")
            self.client.force_login(user)
            response = self.client.get(self._get_perm_url("file_custom_perms"))
            self.assertEqual(response.status_code, 200)
            mock_has_perm.assert_called_with("custom_create", None)

    def test_custom_perm_update(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True) as mock_has_perm:
            user = User.objects.create(username="test")
            self.client.force_login(user)
            existing_record = AsyncFilePermTestModel.objects.create()
            response = self.client.get(self._get_perm_url("file_custom_perms", instance=existing_record))
            self.assertEqual(response.status_code, 200)
            mock_has_perm.assert_called_with("custom_update", existing_record)

    def test_default_perm_create(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True) as mock_has_perm:
            user = User.objects.create(username="test")
            self.client.force_login(user)
            response = self.client.get(self._get_perm_url("file_default_perms"))
            self.assertEqual(response.status_code, 200)
            mock_has_perm.assert_called_with(
                "test_alliance_platform_storage.asyncfilepermtestmodel_create", None
            )

    def test_default_perm_update(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True) as mock_has_perm:
            user = User.objects.create(username="test")
            self.client.force_login(user)
            existing_record = AsyncFilePermTestModel.objects.create()
            response = self.client.get(self._get_perm_url("file_default_perms", instance=existing_record))
            self.assertEqual(response.status_code, 200)
            mock_has_perm.assert_called_with(
                "test_alliance_platform_storage.asyncfilepermtestmodel_update", existing_record
            )

    def test_generate_url_create(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True):
            user = User.objects.create(username="test")
            self.client.force_login(user)
            response = self.client.get(self._get_url())
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(AsyncTempFile.objects.count(), 1)
            async_temp_file = AsyncTempFile.objects.first()
            assert async_temp_file is not None
            self.assertEqual(async_temp_file.original_filename, "abc.jpg")
            self.assertEqual(data["key"], async_temp_file.key)
            self.assertEqual(data["uploadUrl"], f"http://signme.com/{async_temp_file.key}")
            self.assertEqual(async_temp_file.field_name, "file1")
            self.assertEqual(async_temp_file.content_type.model_class(), AsyncFileTestModel)
            self.assertEqual(async_temp_file.moved_to_location, "")

            # Create record using temp file key. This results in move_file being
            # called, AsyncTempFile having `moved_to_location` set and the file field being updated
            # to the original filename
            file = AsyncFileTestModel.objects.create(file1=async_temp_file.key)
            self.assertEqual(file.file1, "abc.jpg")
            self.assertEqual(AsyncTempFile.objects.count(), 1)
            self.assertEqual(AsyncTempFile.objects.filter(moved_to_location="abc.jpg").count(), 1)

    def test_generate_url_update(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True):
            user = User.objects.create(username="test")
            self.client.force_login(user)
            instance = AsyncFileTestModel.objects.create(file1="some/value.jpg")
            response = self.client.get(self._get_url(instance=instance))
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(AsyncTempFile.objects.count(), 1)
            async_temp_file = AsyncTempFile.objects.first()
            assert async_temp_file is not None
            self.assertEqual(async_temp_file.original_filename, "abc.jpg")
            self.assertEqual(data["key"], async_temp_file.key)
            self.assertEqual(data["uploadUrl"], f"http://signme.com/{async_temp_file.key}")
            self.assertEqual(async_temp_file.field_name, "file1")
            self.assertEqual(async_temp_file.content_type.model_class(), AsyncFileTestModel)
            self.assertEqual(async_temp_file.moved_to_location, "")

            # Update the file1 to use the new temp key. This results in move_file being
            # called, AsyncTempFile having `moved_to_location` set and the file field being updated
            # to the original filename
            instance.file1 = async_temp_file.key
            instance.save()
            self.assertEqual(AsyncTempFile.objects.count(), 1)
            self.assertEqual(AsyncTempFile.objects.filter(moved_to_location="abc.jpg").count(), 1)


class DownloadRedirectViewTestCase(TestCase):
    def _get_url(self, instance: AsyncFileTestModel, filename="abc.jpg"):
        field_id = default_async_field_registry.generate_id(AsyncFileTestModel._meta.get_field("file1"))
        query_params = dict(fieldId=field_id, filename=filename, instanceId=instance.pk)
        return f"{reverse(default_async_field_registry.attached_download_view)}?{urlencode(query_params)}"

    def _get_perm_url(
        self,
        instance: AsyncFilePermTestModel,
        field_name: Literal["file_no_perms", "file_custom_perms", "file_default_perms"],
        filename="abc.jpg",
    ):
        """Return a URL for the AsyncFilePermTestModel"""
        field_id = default_async_field_registry.generate_id(
            cast(AsyncFileField, AsyncFilePermTestModel._meta.get_field(field_name))
        )
        query_params = dict(fieldId=field_id, filename=filename, instanceId=instance.pk)
        return f"{reverse(default_async_field_registry.attached_download_view)}?{urlencode(query_params)}"

    def test_validation(self):
        tests = [
            ({}, {"filename": ["This field is required."], "fieldId": ["This field is required."]}),
            ({"filename": "abc.jpg", "field_id": "invalid"}, {"fieldId": ["Unknown fieldId"]}),
        ]
        for params, errors in tests:
            with self.subTest(params=params):
                url = f"{reverse(default_async_field_registry.attached_view)}?{urlencode(params)}"
                response = self.client.get(url)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), errors)

    def test_no_permission_required(self):
        record = AsyncFilePermTestModel.objects.create(file_no_perms="test.png")
        response = self.client.get(self._get_perm_url(record, "file_no_perms"))
        self.assertRedirects(response, "http://downloadme.com/test.png", fetch_redirect_response=False)

    def test_perm_denied(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=False):
            user = User.objects.create(username="test")
            self.client.force_login(user)
            existing_record = AsyncFilePermTestModel.objects.create(file_no_perms="test.png")
            response = self.client.get(self._get_perm_url(existing_record, "file_custom_perms"))
            self.assertEqual(response.status_code, 403)

    def test_no_value(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True):
            user = User.objects.create(username="test")
            self.client.force_login(user)
            existing_record = AsyncFilePermTestModel.objects.create()
            response = self.client.get(self._get_perm_url(existing_record, "file_custom_perms"))
            self.assertEqual(response.status_code, 404)

    def test_custom_perm(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True) as mock_has_perm:
            user = User.objects.create(username="test")
            self.client.force_login(user)
            existing_record = AsyncFilePermTestModel.objects.create(file_custom_perms="test.png")
            response = self.client.get(self._get_perm_url(existing_record, "file_custom_perms"))
            mock_has_perm.assert_called_with("custom_detail", existing_record)
            self.assertRedirects(response, "http://downloadme.com/test.png", fetch_redirect_response=False)

    def test_default_perm(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True) as mock_has_perm:
            user = User.objects.create(username="test")
            self.client.force_login(user)
            existing_record = AsyncFilePermTestModel.objects.create(file_default_perms="test.png")
            response = self.client.get(self._get_perm_url(existing_record, "file_default_perms"))
            mock_has_perm.assert_called_with(
                "test_alliance_platform_storage.asyncfilepermtestmodel_detail", existing_record
            )
            self.assertRedirects(response, "http://downloadme.com/test.png", fetch_redirect_response=False)

    def test_redirects_to_download(self):
        with patch("test_alliance_platform_storage.models.User.has_perm", return_value=True):
            user = User.objects.create()
            record = AsyncFileTestModel.objects.create(file1="test.png")
            self.client.force_login(user=user)
            response = self.client.get(self._get_url(record, "test.png"))
            self.assertRedirects(response, "http://downloadme.com/test.png", fetch_redirect_response=False)
