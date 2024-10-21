import os
import shutil
import tempfile

from django.conf import STATICFILES_STORAGE_ALIAS
from django.conf import settings
from django.contrib.staticfiles import storage
from django.core.management import call_command
from django.template import Context
from django.template import Template
from django.test import SimpleTestCase
from django.test import override_settings


@override_settings(
    STORAGES={
        **settings.STORAGES,
        STATICFILES_STORAGE_ALIAS: {
            "BACKEND": "alliance_platform.storage.staticfiles.storage.ExcludingManifestStaticFilesStorage",
            "OPTIONS": {"exclude_patterns": ["manifest_test/build/*", "*.pdf"]},
        },
    },
)
class TestExcludingManifestStaticFilesStorage(SimpleTestCase):
    """
    Tests for ExcludingManifestStaticFilesStorage
    """

    def setUp(self):
        super().setUp()
        temp_dir = tempfile.mkdtemp()
        # Override the STATIC_ROOT for all tests from setUp to tearDown
        # rather than as a context manager
        self.static_root = temp_dir
        patched_settings = self.settings(STATIC_ROOT=temp_dir)
        patched_settings.enable()
        call_command(
            "collectstatic",
            interactive=False,
            verbosity=0,
        )
        self.addCleanup(shutil.rmtree, temp_dir)
        self.addCleanup(patched_settings.disable)

    def render_template(self, template, **kwargs):
        if isinstance(template, str):
            template = Template(template)
        return template.render(Context(**kwargs)).strip()

    def static_template_snippet(self, path, asvar=False):
        if asvar:
            return "{%% load static from static %%}{%% static '%s' as var %%}{{ var }}" % path
        return "{%% load static from static %%}{%% static '%s' %%}" % path

    def hashed_file_path(self, path):
        fullpath = self.render_template(self.static_template_snippet(path))
        return fullpath.removeprefix(settings.STATIC_URL)

    def test_hash_ignored(self):
        self.assertEqual(
            self.hashed_file_path("manifest_test/build/main-efg456.js"), "manifest_test/build/main-efg456.js"
        )
        self.assertEqual(
            self.hashed_file_path("manifest_test/build/body-abc123.png"),
            "manifest_test/build/body-abc123.png",
        )
        self.assertEqual(self.hashed_file_path("manifest_test/info.pdf"), "manifest_test/info.pdf")

    def test_excluded_files_not_hashed(self):
        # build/main-efg456.js should not be hashed
        relpath = self.hashed_file_path("manifest_test/build/main-efg456.js")
        self.assertEqual(relpath, "manifest_test/build/main-efg456.js")

        # build/body-abc123.png should not be hashed
        relpath = self.hashed_file_path("manifest_test/build/body-abc123.png")
        self.assertEqual(relpath, "manifest_test/build/body-abc123.png")

        # info.pdf should not be hashed
        relpath = self.hashed_file_path("manifest_test/info.pdf")
        self.assertEqual(relpath, "manifest_test/info.pdf")

    def test_manifest(self):
        # Check that the manifest file exists and contains the correct mappings
        manifest_path = os.path.join(self.static_root, "staticfiles.json")
        with open(manifest_path, "r") as f:
            manifest = f.read()
            # Check that hashed files are in the manifest
            self.assertIn('"manifest_test/css/base.css"', manifest)
            self.assertIn('"manifest_test/css/base.', manifest)
            self.assertIn('"manifest_test/images/header.png"', manifest)
            self.assertIn('"manifest_test/images/header.', manifest)
            # Check that excluded files are not hashed in the manifest
            self.assertNotIn('"manifest_test/build/main-efg456.js"', manifest)
            self.assertNotIn('"manifest_test/build/main-efg456.', manifest)
            self.assertNotIn('"manifest_test/info.pdf"', manifest)
            self.assertNotIn('"manifest_test/info.', manifest)

    def test_non_hashed_references(self):
        relpath = self.hashed_file_path("manifest_test/css/base.css")
        self.assertRegex(relpath, r"^manifest_test/css/base\.[0-9a-f]{12}\.css$")
        # Read the content of the collected css file
        with storage.staticfiles_storage.open(relpath) as f:
            content = f.read()
            # Check that reference to header.png is hashed
            self.assertRegex(content.decode(), r"\.\./images/header\.[0-9a-f]{12}\.png")
            # Check that reference to body-abc123.png is not hashed (excluded)
            self.assertIn("../build/body-abc123.png", content.decode())

    def test_collectstatic_output(self):
        # Run collectstatic again and capture the output
        from io import StringIO

        shutil.rmtree(self.static_root)
        out = StringIO()
        call_command("collectstatic", interactive=False, verbosity=2, stdout=out)
        output = out.getvalue()
        # Check that excluded files are not post-processed
        self.assertIn("Post-processed 'manifest_test/css/base.css'", output)
        self.assertIn("Post-processed 'manifest_test/images/header.png'", output)
        self.assertNotIn("Post-processed 'manifest_test/build/main-efg456.js'", output)
        self.assertNotIn("Post-processed 'manifest_test/info.pdf'", output)
