from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from alliance_platform.frontend.bundler.context import get_all_templates_files
from alliance_platform.frontend.checks import FRONTEND_BUILD_CHECK_TAG
from alliance_platform.frontend.management.commands.extract_frontend_resources import Command
from alliance_platform.frontend.management.commands.extract_frontend_resources import (
    extract_resources_from_templates,
)
from django.conf import settings
from django.core import checks
from django.core.checks.registry import registry
from django.core.management import call_command
from django.test import SimpleTestCase
from django.test import override_settings


def failing_build_check(app_configs=None, **kwargs):
    return [checks.Error("The installed frontend package is incompatible", id="test_frontend.E001")]


def warning_build_check(app_configs=None, **kwargs):
    return [checks.Warning("The installed frontend package is outdated", id="test_frontend.W001")]


class ExtractFrontendResourcesBuildCheckTestCase(SimpleTestCase):
    def setUp(self):
        output_dir = TemporaryDirectory()
        self.addCleanup(output_dir.cleanup)
        self.output_path = Path(output_dir.name) / "resources.json"

    def register_build_check(self, check):
        registry.register(check, FRONTEND_BUILD_CHECK_TAG)
        self.addCleanup(registry.registered_checks.discard, check)

    def test_build_check_error_fails_the_command(self):
        self.register_build_check(failing_build_check)
        stderr = StringIO()
        command = Command(stdout=StringIO(), stderr=stderr)
        # --skip-checks skips Django's own run of every check, not the build checks
        with self.assertRaises(SystemExit) as exit_context:
            command.run_from_argv(
                [
                    "manage.py",
                    "extract_frontend_resources",
                    "--skip-checks",
                    "--output",
                    str(self.output_path),
                ]
            )
        self.assertEqual(exit_context.exception.code, 1)
        self.assertIn(
            "?: (test_frontend.E001) The installed frontend package is incompatible", stderr.getvalue()
        )
        self.assertIn(
            f"CommandError: The system checks tagged '{FRONTEND_BUILD_CHECK_TAG}' reported 1 error(s)",
            stderr.getvalue(),
        )
        self.assertFalse(self.output_path.exists())

    @override_settings(SILENCED_SYSTEM_CHECKS=["test_frontend.E001"])
    def test_silenced_errors_and_warnings_do_not_fail_the_command(self):
        self.register_build_check(failing_build_check)
        self.register_build_check(warning_build_check)
        stderr = StringIO()
        call_command(
            "extract_frontend_resources", "--quiet", "--output", str(self.output_path), stderr=stderr
        )
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("resources", json.loads(self.output_path.read_text()))


class ExtractResourcesFromTemplatesTestCase(SimpleTestCase):
    def test_template_outside_the_bundler_root_that_fails_to_parse(self):
        # The template files are cached; rescan with the extra template dir and again after
        get_all_templates_files.cache_clear()
        self.addCleanup(get_all_templates_files.cache_clear)
        with TemporaryDirectory() as template_dir:
            template_path = Path(template_dir) / "broken.html"
            template_path.write_text("{% load not_a_template_library %}")
            templates = [{**settings.TEMPLATES[0], "DIRS": [template_dir]}]
            with override_settings(TEMPLATES=templates):
                _, _, _, warnings = extract_resources_from_templates()
        self.assertIn(
            f"Failed to parse {template_path} - any tags in that file will be ignored",
            warnings,
        )
