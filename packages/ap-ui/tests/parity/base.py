from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any
from unittest import mock
import warnings

from alliance_platform.frontend.bundler.context import BundlerAssetContext
from django.template import Context
from django.template import Template
from django.test import SimpleTestCase

from tests.test_utils import override_ap_frontend_settings
from tests.test_utils.bundler import TestViteBundler
from tests.test_utils.bundler import bundler_kwargs
from tests.test_utils.bundler import bypass_frontend_resource_registry

from .normalizers import normalize_html_fragment
from .style_mocks import make_style_mapping_resolver

test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


class HtmlUIParityTestCase(SimpleTestCase):
    fixture_component: str

    @contextmanager
    def setup_render_context(self):
        with override_ap_frontend_settings(BUNDLER=test_development_bundler):
            with BundlerAssetContext(
                skip_checks=True,
                frontend_resource_registry=bypass_frontend_resource_registry,
            ) as asset_context:
                with mock.patch(
                    "alliance_platform.ui.templatetags.alliance_platform.html_components.base.resolve_vanilla_extract_class_mapping",
                    side_effect=make_style_mapping_resolver(),
                ):
                    yield asset_context

    def load_fixture(self):
        fixture_path = (
            Path(__file__).resolve().parent.parent / "fixtures" / f"ui_html_{self.fixture_component}_parity.json"
        )
        return json.loads(fixture_path.read_text())

    def render_ui_template(self, template_body: str, context_kwargs: dict[str, Any] | None = None) -> str:
        template_obj = Template("{% load alliance_platform.ui %}" + template_body)
        context_obj = Context(context_kwargs or {})
        context_obj.template = template_obj
        return template_obj.render(context_obj)

    def assert_parity_case(self, case: dict[str, Any], context_kwargs: dict[str, Any] | None = None):
        with self.setup_render_context() as _asset_context:
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(case["template"], context_kwargs)

        actual_html = normalize_html_fragment(output)
        expected_html = normalize_html_fragment(case["expected_html"])
        self.assertEqual(actual_html, expected_html)

        expected_warnings = case.get("expected_warnings", [])
        actual_warnings = [str(item.message) for item in caught_warnings]
        self.assertEqual(actual_warnings, expected_warnings)
