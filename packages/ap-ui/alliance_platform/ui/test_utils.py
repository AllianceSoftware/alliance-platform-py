"""Test helpers for projects that write their own static ``{% ui %}`` components."""

from __future__ import annotations

from contextlib import ExitStack
from contextlib import contextmanager
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from typing import Iterator
from typing import Mapping
from unittest import mock

from alliance_platform.frontend.bundler.base import BaseBundler
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.frontend.bundler.resource_registry import FrontendResourceRegistry
from alliance_platform.ui.html_components import base as _renderer_base
from alliance_platform.ui.html_components import diagnostics as _diagnostics
from django.conf import settings
from django.template import Context
from django.template import Template
from django.test import SimpleTestCase
from django.test import override_settings

#: Class name data for vanilla-extract stylesheets, keyed by the stylesheet's file name (or a longer
#: trailing path such as ``"stat/styles.css.ts"`` to tell apart stylesheets that share a name).
#: Each value has the shape of the mapping file ``@alliancesoftware/vite-plugin-django-vanilla-extract``
#: writes: a class string per style, or a nested dict for variants and recipes.
StyleMappings = Mapping[str, Mapping[str, Any]]


class _StyleMapping:
    """Dict-backed stand-in for ``VanillaExtractClassMapping``.

    It has the real class's public shape: ``filename`` is the stylesheet path, ``mapping`` and
    ``get_mapping()`` the class data (``None`` when the mapping is unavailable), and a style read
    as an attribute returns its class string or nested dict, or ``""`` when there is none.
    """

    def __init__(self, filename: Path, mapping: Mapping[str, Any] | None):
        self.filename = filename
        self.mapping: dict[str, Any] | None = dict(mapping) if mapping is not None else None

    def get_mapping(self) -> dict[str, Any] | None:
        """Return the class data, or ``None`` when the mapping is unavailable."""
        return self.mapping

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in ("filename", "mapping"):
            raise AttributeError(name)
        return (self.mapping or {}).get(name, "")


def _find_style_mapping(style_mappings: StyleMappings, stylesheet: Path) -> Mapping[str, Any] | None:
    """Return the entry whose key matches the end of ``stylesheet``; the longest key wins."""
    stylesheet_parts = stylesheet.parts
    match: Mapping[str, Any] | None = None
    match_length = 0
    for key, classes in style_mappings.items():
        key_parts = PurePosixPath(key).parts
        if len(key_parts) > match_length and stylesheet_parts[-len(key_parts) :] == key_parts:
            match, match_length = classes, len(key_parts)
    return match


def _override_frontend_settings(**frontend_settings: Any) -> override_settings:
    alliance_platform_settings = getattr(settings, "ALLIANCE_PLATFORM", {})
    return override_settings(
        ALLIANCE_PLATFORM={
            **alliance_platform_settings,
            "FRONTEND": {**alliance_platform_settings.get("FRONTEND", {}), **frontend_settings},
        }
    )


class StaticComponentTestCase(SimpleTestCase):
    """Base test case for static ``{% ui %}`` renderers.

    Compile and render templates inside :meth:`static_render_context`::

        class StatTestCase(StaticComponentTestCase):
            def test_renders_label(self):
                with self.static_render_context({"Stat.css.ts": {"stat": "stat"}}):
                    html = self.render_ui_template('{% ui "stat" label="Open jobs" %}{% endui %}')
                self.assertIn('class="stat"', html)

    Tests that need the database can combine it with Django's ``TestCase``:
    ``class StatTestCase(StaticComponentTestCase, TestCase)``.
    """

    def render_ui_template(self, template_body: str, context: dict[str, Any] | None = None) -> str:
        """Compile ``template_body`` with ``alliance_platform.ui`` loaded and render it.

        Renderers are frontend assets, so call this inside :meth:`static_render_context`.
        """
        template_obj = Template("{% load alliance_platform.ui %}" + template_body)
        context_obj = Context(context or {})
        context_obj.template = template_obj
        return template_obj.render(context_obj)

    @contextmanager
    def static_render_context(
        self,
        style_mappings: StyleMappings | None = None,
        *,
        bundler: BaseBundler | None = None,
        frontend_resource_registry: FrontendResourceRegistry | None = None,
    ) -> Iterator[BundlerAssetContext]:
        """Set up what compiling and rendering static components needs.

        Enters a ``BundlerAssetContext`` with its checks skipped and resolves vanilla-extract class
        mappings from ``style_mappings`` instead of the bundler's mapping files. As at runtime, a
        style missing from a stylesheet's data is reported as a contract problem and resolves to an
        empty class name. A stylesheet with no entry gets its data from
        :meth:`missing_style_mapping`, by default none: it behaves like a mapping file that is not
        available yet, so its classes resolve to empty class names without reports.
        Yields the ``BundlerAssetContext`` so tests can inspect the resources components used.

        Entering the context also forgets which contract diagnostics were already logged, so one
        that an earlier test triggered logs again instead of being deduplicated.

        Args:
            style_mappings: Class names per stylesheet (see :data:`StyleMappings`).
            bundler: Bundler to use instead of the ``BUNDLER`` setting.
            frontend_resource_registry: Resource registry to use instead of the
                ``FRONTEND_RESOURCE_REGISTRY`` setting.
        """
        mappings = style_mappings or {}
        _diagnostics._reset_reported()

        def resolve_mapping(_bundler: BaseBundler, stylesheet: Path) -> Any:
            stylesheet = Path(stylesheet)
            classes = _find_style_mapping(mappings, stylesheet)
            if classes is None:
                classes = self.missing_style_mapping(stylesheet)
            return _StyleMapping(stylesheet, classes)

        with ExitStack() as stack:
            if bundler is not None:
                stack.enter_context(_override_frontend_settings(BUNDLER=bundler))
            asset_context = stack.enter_context(
                BundlerAssetContext(skip_checks=True, frontend_resource_registry=frontend_resource_registry)
            )
            stack.enter_context(
                mock.patch.object(
                    _renderer_base, "resolve_vanilla_extract_class_mapping", new=resolve_mapping
                )
            )
            yield asset_context

    def missing_style_mapping(self, stylesheet: Path) -> Mapping[str, Any] | None:
        """Return class data for a stylesheet that ``style_mappings`` has no entry for.

        Called with the resolved stylesheet path. The default returns ``None``: the stylesheet is
        treated as having no mapping file yet. Override it to supply data or to fail the test.
        """
        return None
