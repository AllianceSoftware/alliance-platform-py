from pathlib import Path
from tempfile import TemporaryDirectory

from alliance_platform.frontend.bundler.context import get_all_templates_files
from alliance_platform.frontend.management.commands.extract_frontend_resources import (
    extract_resources_from_templates,
)
from django.conf import settings
from django.test import SimpleTestCase
from django.test import override_settings


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
