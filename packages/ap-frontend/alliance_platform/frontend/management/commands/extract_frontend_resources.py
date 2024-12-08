from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from typing import Any
from typing import Collection

from django.core.management import BaseCommand
from django.core.management.base import OutputWrapper
from django.template import TemplateSyntaxError
from django.template.loader import get_template

from ...bundler import get_bundler
from ...bundler.context import BundlerAssetContext
from ...bundler.context import get_all_templates_files
from ...settings import ap_frontend_settings


def extract_resources_from_templates() -> tuple[list[Any], dict[str, Collection[str]], list[str], list[str]]:
    """Scans all template files for assets that need to be bundled

    Returns a 4-tuple: list of filenames, breakdown dict, errors and warnings
    """

    all_resources = ap_frontend_settings.FRONTEND_RESOURCE_REGISTRY.get_resources_for_bundling()
    breakdown_templates: dict[str, list[str]] = {}
    breakdown = {
        "registry": list(sorted({str(r.path) for r in all_resources})),
        "templates": breakdown_templates,
    }
    errors: list[str] = []
    warnings: list[str] = []
    with BundlerAssetContext() as asset_context:
        prev = asset_context.get_resources_for_bundling()
        for file in get_all_templates_files():
            # TODO: ability to opt out specific templates?
            try:
                get_template(str(file))
                template_assets = [p for p in asset_context.get_resources_for_bundling() if p not in prev]
                prev = asset_context.get_resources_for_bundling()
                if template_assets:
                    breakdown_templates[str(file)] = sorted({str(p.path) for p in template_assets})
            except TemplateSyntaxError:
                warnings.append(
                    f"Failed to parse {file.relative_to(get_bundler().root_dir)} - any tags in that file will be ignored"
                )
        all_resources.update(asset_context.get_resources_for_bundling())
        breakdown["templates"] = dict(sorted(breakdown_templates.items()))

    node_modules_dir = ap_frontend_settings.NODE_MODULES_DIR

    def transform_resource_data(data: dict):
        path = Path(data["path"])
        if path.is_relative_to(node_modules_dir):
            data["path"] = str(path.relative_to(node_modules_dir))
        return data

    items: list[dict] = []
    for resource in all_resources:
        items.append(transform_resource_data(resource.serialize()))
    return items, breakdown, errors, warnings


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
        ./manage.py extract_frontend_resources --output output.json

        # Will write to stdin and supress other std output
        ./manage extract_frontend_resources --quiet
    """

    help = "Outputs JSON dump of files that need to be bundled for production build"

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
        f = io.StringIO()
        with redirect_stdout(f if quiet else self.stdout):
            resources, breakdown, errors, warnings = extract_resources_from_templates()
            if warnings:
                stderr_warn.write("\n".join(warnings))
            if errors:
                self.stderr.write("\n".join(errors))
            if errors:
                sys.exit(1)
            data = json.dumps({"resources": resources, "breakdown": breakdown})
            if output:
                Path(output).write_text(data)
            else:
                self.stdout.write(data)
