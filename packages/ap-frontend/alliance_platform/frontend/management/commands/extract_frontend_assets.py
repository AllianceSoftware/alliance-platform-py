from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from typing import Any
from typing import Collection

from django.core.management import BaseCommand
from django.core.management.base import OutputWrapper

from .extract_frontend_resources import extract_resources_from_templates

frontend_templates_dir = Path(__file__).parent.parent.parent / "templates"


def extract_asset_filenames() -> tuple[list[Any], dict[str, Collection[str]], list[str], list[str]]:
    """Scans all template files for assets that need to be bundled

    Returns a 4-tuple: list of filenames, breakdown dict, errors and warnings
    """
    resources, breakdown, errors, warnings = extract_resources_from_templates()
    return list(sorted({resource["path"] for resource in resources})), breakdown, errors, warnings


class Command(BaseCommand):
    """
    Extracts used frontend assets from templates used

    This works with any template nodes that extend :class:`~alliance_platform.frontend.bundler.context.BundlerAsset`. All templates
    in the system are loaded to gather all used assets. You can exclude specific directories by setting
    :data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.EXTRACT_ASSETS_EXCLUDE_DIRS`
    to either a :class:`pathlib.Path` or ``re.Pattern``.

    Outputs a valid JSON dump as an array of string paths to files.

    Usage::

        # Will write data to output.json
        ./manage.py extract_frontend_assets --output output.json

        # Will write to stdin and supress other std output
        ./manage extract_frontend_assets --quiet
    """

    help = "Outputs JSON dump of files that need to be bundled for production build. This is deprecated in favour of `extract_frontend_resources`."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet", action="store_true", help="If set any stdout output will be suppressed"
        )
        parser.add_argument(
            "--output",
            help="The path to write the output to. If not set output will be written to stdout",
        )

    def handle(self, *args, quiet=False, output=None, **kwargs):
        stderr_warn = OutputWrapper(sys.stderr)
        stderr_warn.style_func = self.style.WARNING
        stderr_warn.write(
            "`extract_frontend_assets` is deprecated. `extract_frontend_resources` should be used instead, but requires changes to your Vite config - see the upgrade guide."
        )
        f = io.StringIO()
        with redirect_stdout(f if quiet else self.stdout):
            files, breakdown, errors, warnings = extract_asset_filenames()
            if warnings:
                stderr_warn.write("\n".join(warnings))
            if errors:
                self.stderr.write("\n".join(errors))
            if errors:
                sys.exit(1)
            data = json.dumps({"files": files, "breakdown": breakdown})
            if output:
                Path(output).write_text(data)
            else:
                self.stdout.write(data)
