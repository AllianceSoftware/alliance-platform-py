from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock
import warnings

from alliance_platform.frontend.bundler.vanilla_extract import VanillaExtractClassMapping
from alliance_platform.ui.html_components import diagnostics
from alliance_platform.ui.html_components.components import UIButtonRenderer
from alliance_platform.ui.html_components.diagnostics import StaticComponentContractError
from django.template import NodeList
from django.test import SimpleTestCase

from tests.parity.base import test_development_bundler
from tests.test_utils import override_ap_ui_settings

LOGGER = "alliance_platform.ui"
STYLESHEET = Path("/project/node_modules/@alliancesoftware/ui/components/button/Button.css.ts")
CLASSES = {
    "baseButton": "Button_baseButton__1",
    "sizes": {"sm": "Button_sizes_sm__2"},
}


class ReloadingMapping:
    """A mapping whose data gains a style when it is reloaded, as a dev mapping file can."""

    filename = STYLESHEET

    def __init__(self) -> None:
        self.mapping: dict[str, Any] = {"baseButton": "Button_baseButton__1"}

    def get_mapping(self) -> dict[str, Any]:
        self.mapping = {**self.mapping, "iconOnly": "Button_iconOnly__5"}
        return self.mapping

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in ("filename", "mapping"):
            raise AttributeError(name)
        return self.mapping.get(name, "")


class LegacyMapping:
    """A mapping object that exposes its data only as the ``mapping`` attribute."""

    filename = STYLESHEET

    def __init__(self, classes: dict[str, Any]) -> None:
        self.mapping = classes

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in ("filename", "mapping"):
            raise AttributeError(name)
        return self.mapping.get(name, "")


@override_ap_ui_settings(STATIC_COMPONENT_STRICT=False)
class StyleGetterTestCase(SimpleTestCase):
    """The getters against the mapping class used at runtime."""

    def setUp(self):
        super().setUp()
        diagnostics._reset_reported()
        self.addCleanup(diagnostics._reset_reported)
        self.renderer = UIButtonRenderer(
            props={}, nodelist=NodeList(), origin=None, target_var=None, register_asset=False
        )
        # Skip the mapping file handling, and let any attribute miss warn as it does on a later
        # request in development.
        for patcher in (
            mock.patch.object(VanillaExtractClassMapping, "_check_mapping", lambda mapping: None),
            mock.patch.object(VanillaExtractClassMapping, "_should_log_mapping_warning", return_value=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_mapping(self, classes: dict[str, Any] | None) -> VanillaExtractClassMapping:
        def create_mapping(mapping: VanillaExtractClassMapping) -> None:
            mapping.mapping = classes

        with mock.patch.object(VanillaExtractClassMapping, "_create_mapping", create_mapping):
            return VanillaExtractClassMapping(test_development_bundler, STYLESHEET)

    def test_present_styles_resolve_without_reports(self):
        mapping = self.make_mapping(CLASSES)

        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.assertEqual(self.renderer.get_style_class(mapping, "baseButton"), "Button_baseButton__1")
            self.assertEqual(
                self.renderer.get_nested_style_class(mapping, "sizes", "sm"), "Button_sizes_sm__2"
            )

    def test_missing_style_is_reported_once_and_resolves_to_empty(self):
        mapping = self.make_mapping(CLASSES)

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            with self.assertLogs(LOGGER, level="WARNING") as logs:
                self.assertEqual(self.renderer.get_style_class(mapping, "iconOnly"), "")

        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [f"Style 'iconOnly' does not exist in '{STYLESHEET}'"],
        )
        self.assertEqual(getattr(logs.records[0], "kind"), "contract")
        # The mapping class's own missing-class warning is not triggered as well
        self.assertEqual(caught_warnings, [])

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=True)
    def test_missing_style_raises_when_strict(self):
        mapping = self.make_mapping(CLASSES)

        with self.assertRaisesMessage(StaticComponentContractError, "Style 'iconOnly' does not exist"):
            self.renderer.get_style_class(mapping, "iconOnly")

    def test_missing_nested_entries_are_reported(self):
        mapping = self.make_mapping(CLASSES)

        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.assertEqual(self.renderer.get_nested_style_class(mapping, "sizes", "xl"), "")
            self.assertEqual(self.renderer.get_nested_style_class(mapping, "colors", "gray"), "")
            self.assertEqual(self.renderer.get_nested_style_class(mapping, "baseButton", "sm"), "")

        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                f"Style 'sizes.xl' does not exist in '{STYLESHEET}'",
                f"Style 'colors' does not exist in '{STYLESHEET}'",
                f"Style 'baseButton.sm' does not exist in '{STYLESHEET}'",
            ],
        )

    def test_styles_are_checked_against_reloaded_data(self):
        mapping = ReloadingMapping()

        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.assertEqual(self.renderer.get_style_class(mapping, "iconOnly"), "Button_iconOnly__5")

    def test_mapping_attribute_is_checked_without_get_mapping(self):
        mapping = LegacyMapping({"baseButton": "Button_baseButton__1"})

        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.assertEqual(self.renderer.get_style_class(mapping, "baseButton"), "Button_baseButton__1")
            self.assertEqual(self.renderer.get_style_class(mapping, "iconOnly"), "")

        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [f"Style 'iconOnly' does not exist in '{STYLESHEET}'"],
        )

    def test_unavailable_mapping_is_read_as_before_without_reports(self):
        mapping = self.make_mapping(None)

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            with self.assertNoLogs(LOGGER, level="WARNING"):
                self.assertEqual(self.renderer.get_style_class(mapping, "baseButton"), "")
                self.assertEqual(self.renderer.get_nested_style_class(mapping, "sizes", "sm"), "")

        # The mapping class warns that it could not resolve the classes, as it did before
        self.assertTrue(caught_warnings)
        self.assertIn("mapping file was not found", str(caught_warnings[0].message))
