from __future__ import annotations

from contextlib import contextmanager
from functools import cache
import json
import logging
from pathlib import Path
import re
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

from .normalizers import normalize_class_attributes
from .normalizers import normalize_css_var_hashes
from .normalizers import normalize_html_fragment

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
#: Class mappings for every stylesheet a parity case module lists in ``stylesheets``, keyed by the
#: path the renderers request (``@alliancesoftware/ui/components/button/Button.css.ts``) and written
#: by the fixture generator with vanilla-extract's debug identifiers.
CSS_MAPPINGS_PATH = FIXTURES_DIR / "css-mappings.json"
SYNC_FIXTURES_COMMAND = "just sync-html-ui-parity-fixtures ../alliance-platform-js"

test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


@cache
def load_css_mappings() -> dict[str, dict[str, Any]]:
    return json.loads(CSS_MAPPINGS_PATH.read_text())


def load_parity_fixture(component: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / f"ui_html_{component}_parity.json").read_text())


# A vanilla-extract debug identifier starts with its scope, the name of the stylesheet that
# defines the style: Button_baseButton__1a2b3c.
_DEBUG_IDENTIFIER_RE = re.compile(r"([A-Za-z][A-Za-z0-9]*)(?:_[\w-]*)?__[a-z0-9]+")
# Typography classes many styles compose in; the fixtures leave them out too.
_TYPOGRAPHY_SCOPE = "font"


def _class_scopes(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for nested in value.values():
            yield from _class_scopes(nested)
    elif isinstance(value, str):
        for token in value.split():
            if match := _DEBUG_IDENTIFIER_RE.fullmatch(token):
                yield match.group(1)


@cache
def _readable_class_rules() -> tuple[frozenset[str], frozenset[str]]:
    # Every scope a class in the mappings file has except typography, and every fixture's
    # keep_class_tokens.
    scopes = frozenset(_class_scopes(load_css_mappings())) - {_TYPOGRAPHY_SCOPE}
    keep_class_tokens = frozenset(
        token
        for fixture_path in FIXTURES_DIR.glob("ui_html_*_parity.json")
        for token in json.loads(fixture_path.read_text())["keep_class_tokens"]
    )
    return scopes, keep_class_tokens


class _DiagnosticMessages(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord):
        self.messages.append(record.getMessage())


class HtmlUIParityTestCase(StaticComponentTestCase):
    """Renders static components with the real class mappings in ``fixtures/css-mappings.json``.

    :meth:`render_ui_template` and :meth:`render_ui_document` return markup with generated names
    made readable (see :meth:`normalize_generated_names`), so tests assert on ``Button_baseButton``
    rather than ``Button_baseButton__1xyn7kcv``. :meth:`assert_parity_case` reduces the raw output
    with the fixture's own ``class_prefixes`` instead, exactly as the generator reduced React's.
    """

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
            load_css_mappings(),
            bundler=bundler,
            frontend_resource_registry=bypass_frontend_resource_registry,
        ) as asset_context:
            yield asset_context

    def missing_style_mapping(self, stylesheet: Path) -> Mapping[str, Any] | None:
        self.fail(
            f"{CSS_MAPPINGS_PATH.name} has no class mapping for {stylesheet}. List the stylesheet in "
            f"the `stylesheets` of the parity case module for the component that resolves it, then "
            f"run `{SYNC_FIXTURES_COMMAND}`."
        )

    def load_fixture(self) -> dict[str, Any]:
        return load_parity_fixture(self.fixture_component)

    def normalize_generated_names(self, html: str) -> str:
        """Make vanilla-extract generated names readable, as the render helpers do.

        Class attributes go through the fixtures' token rules (see
        :func:`~tests.parity.normalizers.normalize_class_tokens`) with every scope in the mappings
        file allowed except ``font`` typography, which many styles compose in, and with every
        fixture's ``keep_class_tokens``. Hashes are stripped from custom properties set in
        ``style`` attributes.
        """
        scopes, keep_class_tokens = _readable_class_rules()
        return normalize_css_var_hashes(normalize_class_attributes(html, scopes, keep_class_tokens))

    def render_ui_template(self, template_body: str, context: dict[str, Any] | None = None) -> str:
        return self.normalize_generated_names(super().render_ui_template(template_body, context))

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
        return self.normalize_generated_names(BundlerAssetContext.get_current().post_process(output))

    def normalize_static_html(self, html: str, fixture: dict[str, Any]) -> str:
        """Reduce raw static output to what the fixture's ``expected_html`` can be compared with.

        Applies the fixture's class token rules. Components whose static output has extensions
        React's cannot contain extend this to strip them.
        """
        return normalize_class_attributes(html, fixture["class_prefixes"], fixture["keep_class_tokens"])

    def normalize_expected_html(self, html: str) -> str:
        """Hook for components whose fixture markup needs the same stripping as the static output."""
        return html

    def assert_parity_case(self, case: dict[str, Any], context_kwargs: dict[str, Any] | None = None):
        fixture = self.load_fixture()
        with self.setup_render_context() as _asset_context:
            with self.capture_diagnostics() as diagnostics:
                output = StaticComponentTestCase.render_ui_template(self, case["template"], context_kwargs)

        actual_html = normalize_html_fragment(
            self.normalize_static_html(output, fixture),
            ignored_attributes=self.parity_ignored_attributes,
        )
        expected_html = normalize_html_fragment(
            self.normalize_expected_html(case["expected_html"]),
            ignored_attributes=self.parity_ignored_attributes,
        )
        self.assertEqual(actual_html, expected_html)

        self.assertEqual(diagnostics, case.get("expected_warnings", []))
