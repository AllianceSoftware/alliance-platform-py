from datetime import timedelta
from typing import cast

from alliance_platform.storage.async_uploads.models import AsyncFileField
from alliance_platform.storage.async_uploads.models import AsyncTempFile
from django.core.management import BaseCommand
from django.db import models
from django.utils import timezone


class Command(BaseCommand):
    """Command to clean old AsyncTempFile records that accumulate if a file is uploaded but form not submitted

    Usage::

        ./manage.py cleanup_async_temp_files

        # Specify age in hours - anything older is deleted
        ./manage.py cleanup_async_temp_files --age=24
    """

    help = "Cleanup old AsyncTempFile records that accumulate if a file is uploaded but form not submitted"

    def add_arguments(self, parser):
        parser.add_argument(
            "--age",
            action="store",
            default=48,
            type=int,
            help="Only files older than this will be removed (in hours). Defaults to 48.",
        )

        parser.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Don't output number of items removed to stdout",
        )

    def handle(self, *app_labels, **options):
        temp_files = AsyncTempFile.objects.filter(
            created_at__lt=timezone.now() - timedelta(hours=options["age"]), error__isnull=True
        )
        completed_files = temp_files.exclude(moved_to_location="")
        if not options["quiet"]:
            self.stdout.write(
                self.style.NOTICE(f"Found {completed_files.count()} completed temp files for removal")
            )
        completed_files.delete()
        if not options["quiet"]:
            self.stdout.write(
                self.style.NOTICE(f"Found {temp_files.count()} incomplete temp files for removal")
            )
        for temp_file in temp_files:
            field = cast(models.Model, temp_file.content_type.model_class())._meta.get_field(
                temp_file.field_name
            )
            try:
                cast(AsyncFileField, field).storage.delete(temp_file.key)
            except Exception as e:
                if not options["quiet"]:
                    # Ignore any errors from storage and continue processing
                    self.stdout.write(
                        self.style.ERROR(f"Storage failed to remove key {temp_file.key}: {str(e)}")
                    )
            temp_file.delete()
