from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from unittest import mock

from alliance_platform.frontend.bundler.vite import ViteBundler
from alliance_platform.frontend.checks import FRONTEND_BUILD_CHECK_TAG
from alliance_platform.ui.checks import check_static_contract
from alliance_platform.ui.html_components.contract import STATIC_CONTRACT_RELEASES
from alliance_platform.ui.html_components.contract import SUPPORTED_STATIC_CONTRACT_VERSIONS
from django.core.checks import CheckMessage
from django.core.checks import run_checks
from django.test import SimpleTestCase
from test_alliance_platform_ui.bundler import AlliancePlatformPackageResolver

from .test_utils import override_ap_frontend_settings


def make_bundler(root_dir: Path, mode: str = "development") -> ViteBundler:
    """A bundler for ``root_dir`` that resolves the ``@alliancesoftware`` packages in its node_modules"""
    build_dir = root_dir / "build"
    build_dir.mkdir(exist_ok=True)
    (build_dir / "manifest.json").write_text("{}")
    return ViteBundler(
        root_dir=root_dir,
        path_resolvers=[AlliancePlatformPackageResolver(root_dir / "node_modules")],
        build_dir=build_dir,
        server_host="localhost",
        server_port="5273",
        server_protocol="http",
        server_resolve_package_url="redirect-package-url",
        mode=mode,
        disable_ssr=True,
    )


UI_PACKAGE = "@alliancesoftware/ui"
#: The ui contract version the renderers support and the first release that ships it
UI_VERSION = SUPPORTED_STATIC_CONTRACT_VERSIONS[UI_PACKAGE]
UI_RELEASE = STATIC_CONTRACT_RELEASES[UI_PACKAGE][UI_VERSION]
UI_INSTALL_HINT = (
    f"Install {UI_PACKAGE}@{UI_RELEASE} or a later release that ships static contract version {UI_VERSION}."
)


class StaticContractCheckTestCase(SimpleTestCase):
    def setUp(self):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root_dir = Path(temp_dir.name)
        # Laid out like node_modules with both packages installed at the supported versions
        self.node_modules_dir = self.root_dir / "node_modules"
        self.ui_dir = self.node_modules_dir / "@alliancesoftware/ui"
        self.icons_dir = self.node_modules_dir / "@alliancesoftware/icons"
        self.ui_dir.mkdir(parents=True)
        (self.icons_dir / "static-svg/outlined").mkdir(parents=True)
        self.write_contract(self.ui_dir, f'{{ "version": {UI_VERSION} }}')
        self.write_contract(self.icons_dir, '{ "version": 1 }')
        (self.ui_dir / "static-runtime.auto.ts").write_text("export {};\n")
        self.bundler = make_bundler(self.root_dir)
        settings_override = override_ap_frontend_settings(
            BUNDLER=self.bundler, NODE_MODULES_DIR=self.node_modules_dir
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def write_contract(self, package_dir: Path, content: str):
        (package_dir / "static-contract.json").write_text(content)

    def assert_one_error(self, messages: list[CheckMessage], error_id: str) -> CheckMessage:
        self.assertEqual([message.id for message in messages], [error_id])
        self.assertTrue(messages[0].is_serious())
        return messages[0]

    def test_installed_packages_match(self):
        self.assertEqual(check_static_contract(), [])

    def test_missing_contract_file(self):
        (self.ui_dir / "static-contract.json").unlink()
        error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E001")
        self.assertIn("Cannot resolve '@alliancesoftware/ui/static-contract.json'", error.msg)
        self.assertIn(f"'{self.ui_dir / 'static-contract.json'}' does not exist", error.msg)
        self.assertEqual(error.hint, UI_INSTALL_HINT)

    def test_invalid_json(self):
        self.write_contract(self.icons_dir, '{ "version": 1')
        error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E003")
        self.assertIn(f"'{self.icons_dir / 'static-contract.json'}' is not valid JSON", error.msg)
        self.assertEqual(
            error.hint,
            "Install @alliancesoftware/icons@0.0.14 or a later release that ships static contract version 1.",
        )

    def test_no_integer_version(self):
        contract_path = self.ui_dir / "static-contract.json"
        for content, problem in [
            ("{}", "has no 'version'"),
            ("[1]", "has no 'version'"),
            ('{ "version": "1" }', "has a 'version' that is not an integer: \"1\""),
            ('{ "version": 1.0 }', "has a 'version' that is not an integer: 1.0"),
            ('{ "version": true }', "has a 'version' that is not an integer: true"),
        ]:
            with self.subTest(content):
                self.write_contract(self.ui_dir, content)
                error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E001")
                self.assertEqual(error.msg, f"'{contract_path}' {problem}.")

    def test_newer_ui_contract(self):
        newer = UI_VERSION + 1
        self.write_contract(self.ui_dir, f'{{ "version": {newer} }}')
        error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E002")
        self.assertEqual(
            error.msg,
            f"Static contract mismatch for @alliancesoftware/ui: installed version {newer}, "
            f"alliance-platform-ui supports {UI_VERSION} (read from '{self.ui_dir / 'static-contract.json'}').",
        )
        self.assertEqual(
            error.hint,
            f"Downgrade to @alliancesoftware/ui@{UI_RELEASE} or a later release that ships static contract "
            f"version {UI_VERSION}, or upgrade alliance-platform-ui to a release that supports version {newer}.",
        )

    def test_older_ui_contract(self):
        # Release 1 of the static components shipped contract version 1
        self.write_contract(self.ui_dir, '{ "version": 1 }')
        error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E002")
        self.assertEqual(
            error.msg,
            f"Static contract mismatch for @alliancesoftware/ui: installed version 1, "
            f"alliance-platform-ui supports {UI_VERSION} (read from '{self.ui_dir / 'static-contract.json'}').",
        )
        self.assertEqual(
            error.hint,
            f"Upgrade to @alliancesoftware/ui@{UI_RELEASE} or a later release that ships static contract "
            f"version {UI_VERSION}.",
        )

    def test_older_icons_contract(self):
        with (
            mock.patch.dict(SUPPORTED_STATIC_CONTRACT_VERSIONS, {"@alliancesoftware/icons": 2}),
            mock.patch.dict(STATIC_CONTRACT_RELEASES["@alliancesoftware/icons"], {2: "0.0.20"}),
        ):
            error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E004")
        self.assertEqual(
            error.msg,
            "Static contract mismatch for @alliancesoftware/icons: installed version 1, "
            f"alliance-platform-ui supports 2 (read from '{self.icons_dir / 'static-contract.json'}').",
        )
        self.assertEqual(
            error.hint,
            "Upgrade to @alliancesoftware/icons@0.0.20 or a later release that ships static contract "
            "version 2.",
        )

    def test_hint_without_a_recorded_release(self):
        with mock.patch.dict(SUPPORTED_STATIC_CONTRACT_VERSIONS, {"@alliancesoftware/icons": 2}):
            error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E004")
        self.assertEqual(
            error.hint,
            "Upgrade to the @alliancesoftware/icons release that ships static contract version 2.",
        )

    def test_every_supported_version_has_a_recorded_release(self):
        for package, version in SUPPORTED_STATIC_CONTRACT_VERSIONS.items():
            with self.subTest(package):
                self.assertIn(version, STATIC_CONTRACT_RELEASES[package])

    def test_static_svg_directory(self):
        static_svg_dir = self.icons_dir / "static-svg"
        shutil.rmtree(static_svg_dir)
        error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E005")
        self.assertIn(
            "Cannot resolve the static SVG icon directory '@alliancesoftware/icons/static-svg'", error.msg
        )
        self.assertEqual(
            error.hint,
            "Install @alliancesoftware/icons@0.0.14 or a later release that ships static contract version 1.",
        )

        static_svg_dir.write_text("")
        error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E005")
        self.assertEqual(
            error.msg,
            "The static SVG icon directory '@alliancesoftware/icons/static-svg' resolved to "
            f"'{static_svg_dir}', which is not a directory.",
        )

    def test_missing_runtime_entry(self):
        (self.ui_dir / "static-runtime.auto.ts").unlink()
        error = self.assert_one_error(check_static_contract(), "alliance_platform_ui.E006")
        self.assertIn(
            "Cannot resolve the static runtime entry '@alliancesoftware/ui/static-runtime.auto.ts'",
            error.msg,
        )
        self.assertEqual(error.hint, UI_INSTALL_HINT)

    def test_resolution_failures_are_reported(self):
        with mock.patch.object(self.bundler, "resolve_path", side_effect=RuntimeError("Resolver failed")):
            messages = check_static_contract()
        self.assertEqual(
            [message.id for message in messages],
            [
                "alliance_platform_ui.E001",
                "alliance_platform_ui.E003",
                "alliance_platform_ui.E005",
                "alliance_platform_ui.E006",
            ],
        )
        for message in messages:
            self.assertIn("Resolver failed", message.msg)

    def test_skipped_without_node_modules(self):
        shutil.rmtree(self.node_modules_dir)
        self.assertEqual(check_static_contract(), [])

    def test_skipped_outside_development_mode(self):
        shutil.rmtree(self.ui_dir)
        with override_ap_frontend_settings(BUNDLER=make_bundler(self.root_dir, mode="production")):
            self.assertEqual(check_static_contract(), [])

    def test_runs_with_the_frontend_build_checks(self):
        self.write_contract(self.ui_dir, f'{{ "version": {UI_VERSION + 1} }}')
        messages = run_checks(tags=[FRONTEND_BUILD_CHECK_TAG])
        self.assertIn("alliance_platform_ui.E002", [message.id for message in messages])
