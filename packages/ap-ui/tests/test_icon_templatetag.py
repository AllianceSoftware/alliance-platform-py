from contextlib import contextmanager
from unittest import mock

from alliance_platform.frontend.bundler.context import BundlerAssetContext
from django.template import Context
from django.template import Template
from django.template import TemplateSyntaxError
from django.test import SimpleTestCase

from .test_utils import override_ap_frontend_settings
from .test_utils.bundler import TestViteBundler
from .test_utils.bundler import bundler_kwargs
from .test_utils.bundler import bypass_frontend_resource_registry

test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


@override_ap_frontend_settings(
    DEBUG_COMPONENT_OUTPUT=False,
    BUNDLER=test_development_bundler,
)
class IconTemplateTagTestCase(SimpleTestCase):
    @contextmanager
    def setup_overrides(self):
        with override_ap_frontend_settings(BUNDLER=test_development_bundler):
            with BundlerAssetContext(
                skip_checks=True, frontend_resource_registry=bypass_frontend_resource_registry
            ):
                yield

    def _render_icon(self, template_str: str, **context_kwargs):
        tpl = Template("{% load react %}{% load alliance_platform.ui %}" + template_str)
        context = Context(context_kwargs)
        context.template = tpl
        return tpl.render(context)

    def _get_resolve_path_arg(self, template_str: str, **context_kwargs):
        """Render an icon template and capture the path argument passed to resolve_path."""
        captured = {}
        original_resolve_path = test_development_bundler.resolve_path

        def capture_resolve_path(path, *args, **kwargs):
            captured["path"] = path
            return original_resolve_path(path, *args, **kwargs)

        with mock.patch.object(test_development_bundler, "resolve_path", side_effect=capture_resolve_path):
            self._render_icon(template_str, **context_kwargs)
        return captured.get("path")

    def test_default_icon_resolves_to_outlined(self):
        """An icon with no suffix should resolve to the outlined subdirectory."""
        with self.setup_overrides():
            path = self._get_resolve_path_arg('{% Icon "Pencil" %}')
            self.assertEqual(path, "@alliancesoftware/icons/outlined/Pencil")

    def test_solid_suffix_resolves_to_solid(self):
        """An icon ending with Solid should resolve to the solid subdirectory."""
        with self.setup_overrides():
            path = self._get_resolve_path_arg('{% Icon "ChevronDownSolid" %}')
            self.assertEqual(path, "@alliancesoftware/icons/solid/ChevronDownSolid")

    def test_duotone_suffix_resolves_to_duotone(self):
        """An icon ending with DuoTone should resolve to the duotone subdirectory."""
        with self.setup_overrides():
            path = self._get_resolve_path_arg('{% Icon "AlertDuoTone" %}')
            self.assertEqual(path, "@alliancesoftware/icons/duotone/AlertDuoTone")

    def test_duocolor_suffix_resolves_to_duocolor(self):
        """An icon ending with DuoColor should resolve to the duocolor subdirectory."""
        with self.setup_overrides():
            path = self._get_resolve_path_arg('{% Icon "AlertDuoColor" %}')
            self.assertEqual(path, "@alliancesoftware/icons/duocolor/AlertDuoColor")

    def test_solid_suffix_takes_priority_over_outlined(self):
        """Solid suffix should match even if the name also contains other keywords."""
        with self.setup_overrides():
            path = self._get_resolve_path_arg('{% Icon "OutlinedIconSolid" %}')
            self.assertEqual(path, "@alliancesoftware/icons/solid/OutlinedIconSolid")

    def test_icon_name_must_be_static(self):
        """Icon name must be a static string, not a variable."""
        with self.setup_overrides():
            with self.assertRaises(TemplateSyntaxError):
                self._render_icon("{% Icon icon_name %}", icon_name="Pencil")

    def test_icon_renders_with_props(self):
        """Props passed to the Icon tag should appear in the rendered output."""
        with self.setup_overrides():
            output = self._render_icon('{% Icon "Pencil" data-testid="pencil-icon" %}')
            self.assertIn("pencil-icon", output)

    def test_icon_renders_as_named_export(self):
        """The icon component should use the icon name as a named export."""
        with self.setup_overrides():
            output = self._render_icon('{% Icon "Pencil" %}')
            # The generated code should import { Pencil } from the resolved path
            self.assertIn("Pencil", output)

    def test_icon_no_end_tag_required(self):
        """Icon tag should not require an endIcon tag."""
        with self.setup_overrides():
            # This should render without error - no endIcon needed
            output = self._render_icon('{% Icon "Pencil" %}')
            self.assertTrue(len(output.strip()) > 0)

    def test_icon_with_end_tag_raises(self):
        """Using an endIcon tag should raise an error since Icon accepts no children."""
        with self.setup_overrides():
            with self.assertRaises(TemplateSyntaxError):
                self._render_icon('{% Icon "Pencil" %}content{% endIcon %}')
