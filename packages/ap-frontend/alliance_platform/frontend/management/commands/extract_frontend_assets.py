from contextlib import redirect_stdout
from functools import lru_cache
import io
import json
from pathlib import Path
import re
import sys
from typing import Any
from typing import Collection

from django.core.management import BaseCommand
from django.core.management.base import OutputWrapper
from django.template import TemplateSyntaxError
from django.template import engines
from django.template.loader import get_template
from django.template.utils import get_app_template_dirs

from ...bundler import get_bundler
from ...bundler.context import BundlerAssetContext
from ...settings import ap_frontend_settings

frontend_templates_dir = Path(__file__).parent.parent.parent / "templates"


@lru_cache
def get_all_templates_files() -> list[Path]:
    """Scans all template dirs for template files

    Will exclude any templates the match an entry in :data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.EXTRACT_ASSETS_EXCLUDE_DIRS`
    """
    dirs = get_app_template_dirs("templates")
    for engine in engines.all():
        dirs += tuple(engine.template_dirs)
    files: list[Path] = []
    for dir in dirs:
        should_exclude = False
        for excl in ap_frontend_settings.EXTRACT_ASSETS_EXCLUDE_DIRS:
            if isinstance(excl, re.Pattern):
                if excl.match(str(dir)):
                    should_exclude = True
                    break
            elif str(dir).startswith(str(excl)):
                should_exclude = True

        # always include the frontend templates dir even if would otherwise
        # be excluded
        if should_exclude and dir != frontend_templates_dir:
            continue
        files.extend(x for x in Path(dir).glob("**/*.html") if x)
    return files


def extract_asset_filenames() -> tuple[list[Any], dict[str, Collection[str]], list[str], list[str]]:
    """Scans all template files for assets that need to be bundled

    Returns a 4-tuple: list of filenames, breakdown dict, errors and warnings
    """

    all_files = {str(f) for f in ap_frontend_settings.FRONTEND_ASSET_REGISTRY.get_asset_paths()}
    breakdown_templates: dict[str, list[str]] = {}
    breakdown = {
        "registry": list(sorted(all_files)),
        "templates": breakdown_templates,
    }
    errors: list[str] = []
    warnings: list[str] = []
    with BundlerAssetContext() as asset_context:
        prev = asset_context.get_asset_paths()
        for file in get_all_templates_files():
            # TODO: ability to opt out specific templates?
            try:
                get_template(str(file))
                template_assets = [p for p in asset_context.get_asset_paths() if p not in prev]
                prev = asset_context.get_asset_paths()
                if template_assets:
                    breakdown_templates[str(file)] = [str(p) for p in sorted(template_assets)]
            except TemplateSyntaxError:
                warnings.append(
                    f"Failed to parse {file.relative_to(get_bundler().root_dir)} - any tags in that file will be ignored"
                )
        paths = [str(p) for p in asset_context.get_asset_paths()]
        all_files.update(paths)
        breakdown["templates"] = dict(sorted(breakdown_templates.items()))

    node_modules_dir = ap_frontend_settings.NODE_MODULES_DIR

    def transform_path(path: Path):
        if path.is_relative_to(node_modules_dir):
            return str(path.relative_to(node_modules_dir))
        return str(path)

    return [transform_path(Path(f)) for f in all_files], breakdown, errors, warnings


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
        with redirect_stdout(f if quiet else self.stdout):  # type: ignore[type-var]
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
