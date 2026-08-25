from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import warnings

from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.ui.icons import reset_static_icon_cache
from django.conf import settings
from django.template import TemplateSyntaxError

from tests.parity.base import HtmlUIParityTestCase
from tests.parity.style_mocks import make_style_mapping_resolver
from tests.test_utils import override_ap_frontend_settings
from tests.test_utils.bundler import TestViteBundler
from tests.test_utils.bundler import bundler_kwargs
from tests.test_utils.bundler import bypass_frontend_resource_registry


class UIIconComponentTestCase(HtmlUIParityTestCase):
    def setUp(self):
        reset_static_icon_cache()

    def render_with_warnings(self, template_body: str, context_kwargs=None):
        with self.setup_render_context() as asset_context:
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(template_body, context_kwargs)
        return output, [str(item.message) for item in caught_warnings], asset_context

    def test_renders_default_outlined_icon(self):
        output, caught, _ = self.render_with_warnings('{% ui "icon" name="Pencil01Outlined" %}{% endui %}')

        self.assertEqual(caught, [])
        self.assertIn('<span role="img" aria-hidden="true" data-apui-slot="icon"', output)
        self.assertIn('class="Icon_icon Icon_variants_plain Icon_sizes_xs"', output)
        self.assertIn("<svg", output)
        self.assertIn('focusable="false"', output)
        self.assertIn('stroke-width="2"', output)

    def test_collected_assets_document_emits_only_one_inline_icon(self):
        with self.setup_render_context():
            output = self.render_ui_document('{% ui "icon" name="Pencil01Outlined" size="sm" %}{% endui %}')

        self.assertEqual(output.count("<svg"), 1)
        self.assertNotIn("<img", output)
        self.assertIn('class="Icon_icon Icon_variants_plain Icon_sizes_sm"', output)
        self.assertIn('<svg width="24" height="24"', output)

    def test_collected_assets_document_does_not_embed_distinct_icon_images(self):
        with self.setup_render_context():
            output = self.render_ui_document(
                '{% ui "icon" name="Pencil01Outlined" %}{% endui %}'
                '{% ui "icon" name="CheckCircleSolid" %}{% endui %}'
                '{% ui "icon" name="AlertCircleDuoTone" %}{% endui %}'
            )

        self.assertEqual(output.count("<svg"), 3)
        self.assertNotIn("<img", output)

    def test_collected_assets_document_does_not_embed_repeated_icon_images(self):
        with self.setup_render_context():
            output = self.render_ui_document('{% ui "icon" name="Pencil01Outlined" %}{% endui %}' * 3)

        self.assertEqual(output.count("<svg"), 3)
        self.assertNotIn("<img", output)

    def test_renders_solid_duotone_and_duocolor_icons(self):
        output, caught, _ = self.render_with_warnings(
            '{% ui "icon" name="CheckCircleSolid" %}{% endui %}'
            '{% ui "icon" name="AlertCircleDuoTone" %}{% endui %}'
            '{% ui "icon" name="Pencil01DuoColor" %}{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertIn('fill-rule="evenodd"', output)
        self.assertIn('opacity="0.12"', output)
        self.assertIn('opacity="0.4"', output)

    def test_applies_wrapper_props_and_accessible_label(self):
        output, caught, _ = self.render_with_warnings(
            '{% ui "icon" name="Pencil01Outlined" size="sm" variant="circle" color="destructive" '
            'class="extra" id="edit-icon" title="Edit" data_testid="edit" aria_label="Edit" %}{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertIn(
            'class="Icon_icon Icon_variants_circle Icon_colors_destructive Icon_sizes_sm extra"', output
        )
        self.assertIn('id="edit-icon"', output)
        self.assertIn('title="Edit"', output)
        self.assertIn('data-testid="edit"', output)
        self.assertIn('aria-label="Edit"', output)
        self.assertNotIn('aria-hidden="true"', output)

    def test_warns_and_drops_event_handlers_and_children(self):
        output, caught, _ = self.render_with_warnings(
            '{% ui "icon" name="Pencil01Outlined" onClick="alert(1)" %}ignored{% endui %}'
        )

        self.assertIn("'icon' does not support children; the content will be ignored", caught)
        self.assertIn(
            "Event handler prop 'onClick' is not supported by static icon components and will be ignored",
            caught,
        )
        self.assertNotIn("alert", output)
        self.assertNotIn("ignored", output)

    def test_dynamic_name_fails_during_resource_resolution(self):
        with self.setup_render_context():
            with self.assertRaisesMessage(TemplateSyntaxError, "static string literal"):
                self.render_ui_template('{% ui "icon" name=icon_name %}{% endui %}', {"icon_name": "Pencil"})

    def test_lowercase_icon_tag_supports_as_var(self):
        output, caught, _ = self.render_with_warnings(
            '{% icon "Pencil01Outlined" as user_icon %}{{ user_icon }}'
        )

        self.assertEqual(caught, [])
        self.assertIn('<span role="img" aria-hidden="true" data-apui-slot="icon"', output)

    def test_resource_discovery_includes_css_and_specific_icon(self):
        with self.setup_render_context() as asset_context:
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                self.render_ui_template('{% ui "icon" name="Pencil01Outlined" %}{% endui %}')
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        self.assertEqual([str(item.message) for item in caught_warnings], [])
        self.assertTrue(any(path.endswith("@alliancesoftware/icons/Icon.css.ts") for path in resource_paths))
        self.assertTrue(
            any(path.endswith("static-svg/outlined/Pencil01Outlined.svg") for path in resource_paths)
        )
        self.assertFalse(
            any(path.endswith("static-svg/solid/CheckCircleSolid.svg") for path in resource_paths)
        )

    def test_render_loads_only_requested_icon_file(self):
        read_icon_paths: list[Path] = []
        original_read_text = Path.read_text

        def spy_read_text(path: Path, *args, **kwargs):
            if "static-svg" in str(path):
                read_icon_paths.append(path)
            return original_read_text(path, *args, **kwargs)

        with mock.patch("pathlib.Path.read_text", autospec=True, side_effect=spy_read_text):
            output, caught, _ = self.render_with_warnings(
                '{% ui "icon" name="Pencil01Outlined" %}{% endui %}'
            )

        self.assertEqual(caught, [])
        self.assertIn("Pencil01Outlined", str(read_icon_paths[0]))
        self.assertEqual(len(read_icon_paths), 1)
        self.assertIn("<svg", output)

    def test_collected_assets_in_production_resolve_svg_without_embedding_an_image(self):
        icon_source = (
            Path(__file__).resolve().parent / "fixtures/icons/static-svg/outlined/Pencil01Outlined.svg"
        )
        icon_manifest_path = str(icon_source.relative_to(settings.PROJECT_DIR))
        style_manifest_path = "@alliancesoftware/icons/Icon.css.ts"

        with TemporaryDirectory() as temp_dir:
            build_dir = Path(temp_dir)
            icon_output = build_dir / "assets/Pencil01Outlined-built.svg"
            icon_output.parent.mkdir(parents=True)
            icon_output.write_text(icon_source.read_text())
            (build_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        icon_manifest_path: {
                            "file": "assets/Pencil01Outlined-built.svg",
                            "src": icon_manifest_path,
                        },
                        style_manifest_path: {
                            "file": "assets/Icon-built.js",
                            "src": style_manifest_path,
                            "css": ["assets/Icon-built.css"],
                        },
                    }
                )
            )
            production_bundler = TestViteBundler(
                **{**bundler_kwargs, "build_dir": build_dir, "mode": "production"}
            )

            with override_ap_frontend_settings(BUNDLER=production_bundler):
                with BundlerAssetContext(
                    skip_checks=True,
                    frontend_resource_registry=bypass_frontend_resource_registry,
                ) as asset_context:
                    with mock.patch(
                        "alliance_platform.ui.templatetags.alliance_platform.html_components.base.resolve_vanilla_extract_class_mapping",
                        side_effect=make_style_mapping_resolver(),
                    ):
                        output = self.render_ui_document('{% ui "icon" name="Pencil01Outlined" %}{% endui %}')
                    resource_paths = [
                        str(resource.path) for resource in asset_context.get_resources_for_bundling()
                    ]

        self.assertEqual(output.count("<svg"), 1)
        self.assertNotIn("<img", output)
        self.assertIn("/static/assets/Icon-built.css", output)
        self.assertTrue(any(path.endswith("Pencil01Outlined.svg") for path in resource_paths))
