# Generated by Django 4.2.11 on 2024-04-04 10:41

from django.conf import settings
from django.db import migrations
from django.db import models
import django.db.models.deletion

import test_alliance_platform_frontend.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("test_alliance_platform_frontend", "0002_case_insensitive_db_collation"),
    ]

    operations = [
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
                ("email", models.EmailField(db_collation="case_insensitive", max_length=254, unique=True)),
            ],
            options={
                "db_table": "test_alliance_platform_frontend_user",
                "default_permissions": (),
            },
            managers=[
                ("objects", test_alliance_platform_frontend.models.UserManager()),
                (
                    "profiles",
                    test_alliance_platform_frontend.models.UserManager(select_related_profiles=True),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AdminProfile",
            fields=[
                (
                    "user_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "test_alliance_platform_frontend_adminprofile",
            },
            bases=("test_alliance_platform_frontend.user",),
            managers=[
                ("objects", test_alliance_platform_frontend.models.UserManager()),
                (
                    "profiles",
                    test_alliance_platform_frontend.models.UserManager(select_related_profiles=True),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CustomerProfile",
            fields=[
                (
                    "user_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "test_alliance_platform_frontend_customerprofile",
            },
            bases=("test_alliance_platform_frontend.user",),
            managers=[
                ("objects", test_alliance_platform_frontend.models.UserManager()),
                (
                    "profiles",
                    test_alliance_platform_frontend.models.UserManager(select_related_profiles=True),
                ),
            ],
        ),
    ]
