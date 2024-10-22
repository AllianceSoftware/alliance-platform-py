# Generated by Django 5.1.1 on 2024-10-22 09:38

import alliance_platform.storage.async_uploads.models.fields
import django.contrib.auth.models
import django.contrib.auth.validators
from django.db import migrations
from django.db import models
import django.db.models.deletion
import django.utils.timezone

import test_alliance_platform_storage.storage


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlternateRegistryModel",
            fields=[
                (
                    "id",
                    models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                (
                    "file1",
                    alliance_platform.storage.async_uploads.models.fields.AsyncFileField(
                        max_length=500,
                        storage=test_alliance_platform_storage.storage.DummyStorage(),
                        upload_to="",
                    ),
                ),
                (
                    "file2",
                    alliance_platform.storage.async_uploads.models.fields.AsyncFileField(
                        max_length=500,
                        storage=test_alliance_platform_storage.storage.DummyStorage(),
                        upload_to="",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AsyncFilePermTestModel",
            fields=[
                (
                    "id",
                    models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                (
                    "file_no_perms",
                    alliance_platform.storage.async_uploads.models.fields.AsyncFileField(
                        blank=True,
                        max_length=500,
                        null=True,
                        storage=test_alliance_platform_storage.storage.DummyStorage(),
                        upload_to="",
                    ),
                ),
                (
                    "file_default_perms",
                    alliance_platform.storage.async_uploads.models.fields.AsyncFileField(
                        blank=True,
                        max_length=500,
                        null=True,
                        storage=test_alliance_platform_storage.storage.DummyStorage(),
                        upload_to="",
                    ),
                ),
                (
                    "file_custom_perms",
                    alliance_platform.storage.async_uploads.models.fields.AsyncFileField(
                        blank=True,
                        max_length=500,
                        null=True,
                        storage=test_alliance_platform_storage.storage.DummyStorage(),
                        upload_to="",
                    ),
                ),
            ],
            options={
                "db_table": "test_alliance_platform_storage_async_file_perm_test_model",
            },
        ),
        migrations.CreateModel(
            name="AsyncFileTestParentModel",
            fields=[
                (
                    "id",
                    models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
            ],
            options={
                "db_table": "test_alliance_platform_storage_async_file_test_parent_model",
            },
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        error_messages={"unique": "A user with that username already exists."},
                        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                        max_length=150,
                        unique=True,
                        validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                        verbose_name="username",
                    ),
                ),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="email address")),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                (
                    "date_joined",
                    models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined"),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "db_table": "test_alliance_platform_storage_custom_user",
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="AsyncFileTestModel",
            fields=[
                (
                    "id",
                    models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                (
                    "file1",
                    alliance_platform.storage.async_uploads.models.fields.AsyncFileField(
                        blank=True,
                        max_length=500,
                        null=True,
                        storage=test_alliance_platform_storage.storage.DummyStorage(),
                        upload_to="",
                    ),
                ),
                (
                    "image_with_dims",
                    alliance_platform.storage.async_uploads.models.fields.AsyncImageField(
                        blank=True,
                        height_field="image_height",
                        max_length=500,
                        null=True,
                        storage=test_alliance_platform_storage.storage.DummyStorage(),
                        upload_to="",
                        width_field="image_width",
                    ),
                ),
                ("image_width", models.IntegerField(blank=True, null=True)),
                ("image_height", models.IntegerField(blank=True, null=True)),
                (
                    "image_no_dims",
                    alliance_platform.storage.async_uploads.models.fields.AsyncImageField(
                        blank=True,
                        max_length=500,
                        null=True,
                        storage=test_alliance_platform_storage.storage.DummyStorage(),
                        upload_to="",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="files",
                        to="test_alliance_platform_storage.asyncfiletestparentmodel",
                    ),
                ),
            ],
            options={
                "db_table": "test_alliance_platform_storage_async_file_test_model",
            },
        ),
    ]
