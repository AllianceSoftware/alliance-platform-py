# Generated by Django 4.2 on 2023-04-18 00:21
from django.contrib.postgres.operations import CreateCollation
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("test_alliance_platform_ui", "0001_initial"),
    ]

    run_before = []

    operations = [
        CreateCollation("case_insensitive", provider="icu", locale="und-u-ks-level2", deterministic=False),
    ]
