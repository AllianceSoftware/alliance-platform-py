from __future__ import annotations

from contextlib import contextmanager
import json
import logging
from pathlib import Path
from typing import Any
from typing import Iterator
from typing import Mapping

from alliance_platform.frontend.bundler.base import BaseBundler
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.ui.html_components.diagnostics import LOGGER_NAME
from alliance_platform.ui.test_utils import StaticComponentTestCase
from django.template import Context
from django.template import Template

from tests.test_utils.bundler import TestViteBundler
from tests.test_utils.bundler import bundler_kwargs
from tests.test_utils.bundler import bypass_frontend_resource_registry

from .normalizers import normalize_html_fragment
from .style_mocks import DEFAULT_STYLE_MAPPINGS
from .style_mocks import MockVanillaExtractMapping
from .style_mocks import mapping_scope_from_filename

test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


class _DiagnosticMessages(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord):
        self.messages.append(record.getMessage())


class HtmlUIParityTestCase(StaticComponentTestCase):
    fixture_component: str
    parity_ignored_attributes: frozenset[str] = frozenset()

    @contextmanager
    def capture_diagnostics(self) -> Iterator[list[str]]:
        """Collect the messages static components log while the block runs.

        Captures what ``assertLogs("alliance_platform.ui", level="WARNING")`` would, but logging
        nothing is not a failure, so tests can compare against an exact list, including an empty one.
        """
        logger = logging.getLogger(LOGGER_NAME)
        handler = _DiagnosticMessages()
        old_handlers, old_level, old_propagate = logger.handlers[:], logger.level, logger.propagate
        logger.handlers = [handler]
        logger.setLevel(logging.WARNING)
        logger.propagate = False
        try:
            yield handler.messages
        finally:
            logger.handlers = old_handlers
            logger.setLevel(old_level)
            logger.propagate = old_propagate

    @contextmanager
    def setup_render_context(
        self,
        bundler: BaseBundler = test_development_bundler,
    ) -> Iterator[BundlerAssetContext]:
        with self.static_render_context(
            DEFAULT_STYLE_MAPPINGS,
            bundler=bundler,
            frontend_resource_registry=bypass_frontend_resource_registry,
        ) as asset_context:
            yield asset_context

    def _make_style_mapping(self, stylesheet: Path, classes: Mapping[str, Any] | None) -> Any:
        # The fixtures were generated against class names synthesised from the stylesheet and style
        # names, so styles missing from DEFAULT_STYLE_MAPPINGS resolve to a scoped placeholder token.
        return MockVanillaExtractMapping(mapping_scope_from_filename(stylesheet.name), dict(classes or {}))

    def load_fixture(self):
        fixture_path = (
            Path(__file__).resolve().parent.parent
            / "fixtures"
            / f"ui_html_{self.fixture_component}_parity.json"
        )
        return json.loads(fixture_path.read_text())

    def render_ui_document(self, template_body: str, context_kwargs: dict[str, Any] | None = None) -> str:
        """Render and post-process a complete document with collected assets embedded."""
        template_obj = Template(
            "{% load alliance_platform.ui bundler %}"
            "<html><head>{% bundler_embed_collected_assets %}</head>"
            f"<body>{template_body}</body></html>"
        )
        context_obj = Context(context_kwargs or {})
        context_obj.template = template_obj
        output = template_obj.render(context_obj)
        return BundlerAssetContext.get_current().post_process(output)

    def assert_parity_case(self, case: dict[str, Any], context_kwargs: dict[str, Any] | None = None):
        with self.setup_render_context() as _asset_context:
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(case["template"], context_kwargs)

        actual_html = normalize_html_fragment(
            output,
            ignored_attributes=self.parity_ignored_attributes,
        )
        expected_html = normalize_html_fragment(
            case["expected_html"],
            ignored_attributes=self.parity_ignored_attributes,
        )
        self.assertEqual(actual_html, expected_html)

        self.assertEqual(diagnostics, case.get("expected_warnings", []))
