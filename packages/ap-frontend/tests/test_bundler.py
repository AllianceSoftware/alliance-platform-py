from os.path import dirname
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from alliance_platform.frontend.bundler.base import BaseBundler
from alliance_platform.frontend.bundler.base import DevServerCheck
from alliance_platform.frontend.bundler.base import RegExAliasResolver
from alliance_platform.frontend.bundler.base import RelativePathResolver
from alliance_platform.frontend.bundler.base import ResolveContext
from alliance_platform.frontend.bundler.base import SourceDirResolver
from alliance_platform.frontend.bundler.base import html_target_browser
from alliance_platform.frontend.bundler.vite import ViteBundler
from django import template
from django.conf import settings
from django.test import SimpleTestCase
from django.test import TestCase
from django.test import override_settings

from tests.test_utils import override_ap_frontend_settings


class TestBundler(TestCase):
    def test_relative_path_resolver(self):
        resolver = RelativePathResolver()
        # Can't resolve if no source_path specifier in context
        self.assertEqual(None, resolver.resolve("./test", ResolveContext(Path("/root"))))

        # Path.is_file will always return False if the file doesn't exist
        def fake_is_file(p):
            if str(p) == "/root/sub/template.html":
                return True
            return False

        with mock.patch("pathlib.Path.is_file", fake_is_file):
            self.assertEqual(
                Path("/root/sub/test"),
                resolver.resolve("./test", ResolveContext(Path("/root"), "/root/sub/template.html")),
            )
            self.assertEqual(
                Path("/root/test/myfile.js"),
                resolver.resolve(
                    "../test/myfile.js", ResolveContext(Path("/root"), "/root/sub/template.html")
                ),
            )

    def test_regex_alias_resolver(self):
        resolver = RegExAliasResolver(r"^node_modules/", "")
        # Can't resolve if no source_path specifier in context
        self.assertEqual(
            Path("package/test.ts"),
            resolver.resolve("node_modules/package/test.ts", ResolveContext(Path("/root"))),
        )

    def test_source_dir_resolver(self):
        resolver = SourceDirResolver(Path("/project/root/"))
        # Can't resolve if no source_path specifier in context
        self.assertEqual(
            Path("/project/root/package/test.ts"),
            resolver.resolve("package/test.ts", ResolveContext(Path("/root"))),
        )
        self.assertEqual(
            None,
            resolver.resolve("/project/test.ts", ResolveContext(Path("/root"))),
        )


class MockRequestResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


class TestViteBundler(ViteBundler):
    def validate_path(
        self,
        filename: str | Path,
        suffix_whitelist: list[str] | None = None,
        suffix_hint: str | None = None,
        resolve_extensions: list[str] | None = None,
    ) -> Path:
        """For test case don't validate the paths exist"""
        return Path(filename)


class TestBaseBundler(BaseBundler):
    def is_development(self) -> bool:
        return True

    def get_url(self, path: Path | str):
        return str(path)

    def get_embed_items(self, paths, content_type=None):
        return []

    def resolve_ssr_import_path(self, path: Path | str):
        return path

    def get_ssr_url(self):
        return "http://localhost/ssr"

    def check_dev_server(self):
        return DevServerCheck(is_running=False)


class TestNonDevCaseInsensitiveExistBundler(TestBaseBundler):
    def is_development(self) -> bool:
        return False

    def does_asset_exist(self, filename: Path):
        return self._resolve_case_insensitive_path(filename) is not None


class TestCaseSensitiveAssetPathValidation(SimpleTestCase):
    def test_validate_path_raises_on_case_mismatch(self):
        with TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            actual_path = root_dir / "frontend/src/app/views/Myview.tsx"
            actual_path.parent.mkdir(parents=True, exist_ok=True)
            actual_path.write_text("export default {};\n", "utf8")

            bundler = TestBaseBundler(root_dir=root_dir, path_resolvers=[])
            bad_path = root_dir / "frontend/src/app/views/MyView.tsx"
            with self.assertRaisesRegex(template.TemplateSyntaxError, "casing mismatch|requested casing"):
                bundler.validate_path(bad_path)

    def test_validate_path_raises_on_case_mismatch_with_extension_resolution(self):
        with TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            actual_path = root_dir / "frontend/src/app/views/Myview.tsx"
            actual_path.parent.mkdir(parents=True, exist_ok=True)
            actual_path.write_text("export default {};\n", "utf8")

            bundler = TestBaseBundler(root_dir=root_dir, path_resolvers=[])
            bad_path_without_extension = root_dir / "frontend/src/app/views/MyView"
            with self.assertRaisesRegex(template.TemplateSyntaxError, "Myview.tsx"):
                bundler.validate_path(bad_path_without_extension, resolve_extensions=[".ts", ".tsx", ".js"])

    def test_validate_path_allows_correct_case(self):
        with TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            actual_path = root_dir / "frontend/src/app/views/Myview.tsx"
            actual_path.parent.mkdir(parents=True, exist_ok=True)
            actual_path.write_text("export default {};\n", "utf8")

            bundler = TestBaseBundler(root_dir=root_dir, path_resolvers=[])
            self.assertEqual(actual_path, bundler.validate_path(actual_path))

    def test_validate_path_skips_case_mismatch_check_outside_development(self):
        with TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            actual_path = root_dir / "frontend/src/app/views/Myview.tsx"
            actual_path.parent.mkdir(parents=True, exist_ok=True)
            actual_path.write_text("export default {};\n", "utf8")

            bundler = TestNonDevCaseInsensitiveExistBundler(root_dir=root_dir, path_resolvers=[])
            bad_path = root_dir / "frontend/src/app/views/MyView.tsx"
            self.assertEqual(bad_path, bundler.validate_path(bad_path))


class TestViteBundlerTestCase(TestCase):
    def create_bundler(self, **kwargs):
        current_dir = Path(dirname(__file__))
        bundler_kwargs = dict(
            root_dir=settings.PROJECT_DIR,
            path_resolvers=[],
            build_dir=current_dir / "fixtures/build_test",
            server_build_dir=current_dir / "fixtures/server_build_test",
            mode="production",
            server_host="localhost",
            server_port="5273",
            server_protocol="http",
            server_resolve_package_url="redirect-package-url",
        )
        bundler_kwargs.update(kwargs)
        return TestViteBundler(**bundler_kwargs)

    def test_dev_url(self):
        with self.assertRaisesMessage(ValueError, "static_url cannot be a full URL in dev"):
            with override_settings(STATIC_URL="http://mycdn.com/static/"):
                self.create_bundler(mode="development")

        with override_settings(STATIC_URL="/test-static/"):
            bundler = self.create_bundler(mode="development")
            self.assertEqual(
                "http://localhost:5273/test-static/components/Button.css",
                bundler.get_url(Path("components/Button.css")),
            )
            self.assertEqual(
                "http://localhost:5273/test-static/components/Button.tsx",
                bundler.get_url(Path("components/Button.tsx")),
            )

            # If absolute path is used should still work
            self.assertEqual(
                "http://localhost:5273/test-static/components/Button.tsx",
                bundler.get_url(settings.PROJECT_DIR / "components/Button.tsx"),
            )

            self.assertEqual("http://localhost:5273/ssr", bundler.get_development_ssr_url())

    @override_settings(STATIC_URL="/test-static/")
    def test_preview_url(self):
        bundler = self.create_bundler(mode="preview")
        self.assertEqual(
            "/test-static/assets/Button-abc123.css",
            bundler.get_url(Path("components/Button.css")),
        )
        self.assertEqual(
            "/test-static/assets/Button-def456.js",
            bundler.get_url(Path("components/Button.tsx")),
        )

        # If absolute path is used should still work
        self.assertEqual(
            "/test-static/assets/Button-def456.js",
            bundler.get_url(settings.PROJECT_DIR / "components/Button.tsx"),
        )

    @override_settings()
    def test_production_url(self):
        with override_settings(STATIC_URL="/test-static/"):
            bundler = self.create_bundler()
            self.assertEqual(
                "/test-static/assets/Button-abc123.css",
                bundler.get_url(Path("components/Button.css")),
            )
            self.assertEqual(
                "/test-static/assets/Button-def456.js",
                bundler.get_url(Path("components/Button.tsx")),
            )
        with override_settings(STATIC_URL="http://mycdn.com/static/"):
            cdn_bundler = self.create_bundler()
            self.assertEqual(
                "http://mycdn.com/static/assets/Button-abc123.css",
                cdn_bundler.get_url(Path("components/Button.css")),
            )
            self.assertEqual(
                "http://mycdn.com/static/assets/Button-def456.js",
                cdn_bundler.get_url(Path("components/Button.tsx")),
            )

            # If absolute path is used should still work
            self.assertEqual(
                "http://mycdn.com/static/assets/Button-def456.js",
                cdn_bundler.get_url(settings.PROJECT_DIR / "components/Button.tsx"),
            )

    def test_resolve(self):
        root_dir = settings.BASE_DIR
        bundler = self.create_bundler(
            root_dir=root_dir,
            path_resolvers=[
                RelativePathResolver(),
                RegExAliasResolver("^/", ""),
                SourceDirResolver(root_dir / "frontend/src"),
            ],
        )
        # The file needs to exist for is_file to work so hardcode path here - if this file is moved
        # then this test will break and will need to be manually updated
        context = ResolveContext(root_dir, "tests/test_bundler.py")
        self.assertEqual(
            root_dir / "another-app/file.js", bundler.resolve_path("/another-app/file.js", context)
        )

        self.assertEqual(
            root_dir / "tests/file.js",
            bundler.resolve_path("./file.js", context),
        )
        self.assertEqual(
            root_dir / "another-dir/file.js",
            bundler.resolve_path("../another-dir/file.js", context),
        )

    @override_settings(STATIC_URL="/test-static/")
    def test_collect_dependencies(self):
        bundler = self.create_bundler()
        deps = bundler.build_manifest.get_asset("components/TestComponent.tsx").collect_dependencies()
        self.assertEqual(
            deps.get_js_dependencies(),
            [
                "assets/TestComponent-47f28fe1.js",
                "assets/jsx-runtime-a1.js",
                "assets/TestComponentTwo-6347c19f.js",
                "assets/Button-def456.js",
            ],
        )
        self.assertEqual(
            deps.get_css_dependencies(),
            [
                "assets/TestComponent-ab23ac31.css",
                "assets/TestComponentTwo-b99abbde.css",
                "assets/Button-abc123.css",
            ],
        )
        self.assertEqual(deps.get_dynamic_js_dependencies(), ["assets/Input-b2.js"])
        self.assertEqual(deps.get_dynamic_css_dependencies(), ["assets/Input-c4.css"])

        deps2 = bundler.build_manifest.get_asset("components/TestComponentTwo.tsx").collect_dependencies()
        self.assertEqual(
            deps2.get_js_dependencies(),
            ["assets/TestComponentTwo-6347c19f.js", "assets/jsx-runtime-a1.js", "assets/Button-def456.js"],
        )
        deps2.merge(deps)
        self.assertEqual(
            deps2.get_js_dependencies(),
            [
                "assets/TestComponentTwo-6347c19f.js",
                "assets/jsx-runtime-a1.js",
                "assets/Button-def456.js",
                "assets/TestComponent-47f28fe1.js",
            ],
        )

    @override_settings(STATIC_URL="/test-static/")
    def test_embed(self):
        bundler = self.create_bundler()
        test_component_tags = [
            '<link rel="stylesheet" href="/test-static/assets/Button-abc123.css">',
            '<link rel="stylesheet" href="/test-static/assets/TestComponent-ab23ac31.css">',
            '<link rel="stylesheet" href="/test-static/assets/TestComponentTwo-b99abbde.css">',
            '<script src="/test-static/assets/TestComponent-47f28fe1.js" type="module"></script>',
        ]
        tags = [
            item.generate_code(html_target_browser)
            for item in bundler.get_embed_items("components/TestComponent.tsx")
        ]
        self.assertEqual(
            sorted(tags),
            test_component_tags,
        )
        # TestComponentTwo is a dependency of TestComponent so should have same set of tags
        # except for its javascript file. `get_embed_code` only includes the direct JS file for each
        # asset - it's dependencies are assumed to be load by the main asset script.
        self.assertEqual(
            sorted(
                [
                    item.generate_code(html_target_browser)
                    for item in bundler.get_embed_items(
                        [Path("components/TestComponent.tsx"), Path("components/TestComponentTwo.tsx")]
                    )
                ]
            ),
            test_component_tags
            + ['<script src="/test-static/assets/TestComponentTwo-6347c19f.js" type="module"></script>'],
        )

    @override_settings(STATIC_URL="/test-static/")
    def test_embed_standalone_css(self):
        bundler = self.create_bundler()
        items = bundler.get_embed_items("styles/normalize.css")
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0].generate_code(html_target_browser),
            '<link rel="stylesheet" href="/test-static/assets/normalize-x1.css">',
        )

    def test_resolve_ssr_import_path(self):
        bundler = self.create_bundler()
        self.assertEqual(
            bundler.server_build_dir / "Button.mjs",
            bundler.resolve_ssr_import_path("components/Button.tsx"),
        )

    def test_format_code_size_limit(self):
        bundler = self.create_bundler(mode="development")

        def mocked_post(*args, **kwargs):
            return MockRequestResponse({"code": "formatted"}, 200)

        with mock.patch("requests.post", side_effect=mocked_post):
            self.assertEqual(bundler.format_code("a short string"), "formatted")
            long_string = "." * 1024 * 1024
            self.assertEqual(bundler.format_code(long_string), long_string)
            with override_ap_frontend_settings(DEV_CODE_FORMAT_LIMIT=0):
                self.assertEqual(bundler.format_code(long_string), "formatted")

    def test_format_code_timeout(self):
        bundler = self.create_bundler(mode="development")

        def mocked_post(*args, **kwargs):
            return MockRequestResponse({"code": "formatted"}, 200)

        with mock.patch("requests.post", side_effect=mocked_post) as mock_send:
            bundler.format_code("code")
            self.assertEqual(mock_send.call_args.kwargs.get("timeout"), 1)

        with mock.patch("requests.post", side_effect=mocked_post) as mock_send:
            with override_ap_frontend_settings(DEV_CODE_FORMAT_TIMEOUT=10):
                bundler.format_code("code")
                self.assertEqual(mock_send.call_args.kwargs.get("timeout"), 10)
