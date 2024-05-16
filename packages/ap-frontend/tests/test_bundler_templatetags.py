import datetime
import json
from typing import cast
from unittest import mock

from alliance_platform.codegen.printer import TypescriptPrinter
from alliance_platform.frontend.bundler.base import HtmlGenerationTarget
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.frontend.bundler.ssr import SSRJsonEncoder
from alliance_platform.frontend.bundler.ssr import SSRSerializerContext
from alliance_platform.frontend.bundler.vanilla_extract import resolve_vanilla_extract_cache_names
from alliance_platform.frontend.templatetags.react import ComponentNode
from alliance_platform.frontend.templatetags.react import ComponentProps
from alliance_platform.frontend.templatetags.react import ComponentSourceCodeGenerator
from django.conf import settings
from django.template import Context
from django.template import Template
from django.test import SimpleTestCase
from django.test import override_settings
from django.utils.functional import SimpleLazyObject
from django.utils.functional import lazy
from django.utils.safestring import mark_safe
from django.utils.timezone import make_aware

from .test_utils import override_ap_frontend_settings
from .test_utils.bundler import TestViteBundler
from .test_utils.bundler import bundler_kwargs
from .test_utils.bundler import bypass_frontend_asset_registry
from .test_utils.bundler import fixtures_dir
from .test_utils.bundler import format_code
from .test_utils.bundler import run_prettier

inline_css_prod = {
    fixtures_dir / "build_test/assets/Button-abc123.css": ".prod_button { color: red; }",
}


def mock_read_text(path):
    if path in inline_css_prod:
        return inline_css_prod[path]
    raise NotImplementedError(f"Mock read_text not implemented for {path}")


def mock_create_mapping(self):
    # Bypass the requests to the dev server VanillaExtractMapping does. They still work
    # but will log warnings because dev server won't be running
    self._load_mapping()


@override_settings(STATIC_URL="/static/")
@mock.patch(
    "alliance_platform.frontend.bundler.vanilla_extract.VanillaExtractClassMapping._create_mapping",
    mock_create_mapping,
)
class TestBundlerTemplateTags(SimpleTestCase):
    def setUp(self) -> None:
        self.test_production_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="production",
        )

        self.test_development_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="development",
        )
        self.dev_url = self.test_development_bundler.dev_server_url

    def test_bundler_url(self):
        for bundler_name, expected in [
            ("test_development_bundler", f"{self.dev_url}components/Button.css"),
            ("test_production_bundler", "/static/assets/Button-abc123.css"),
        ]:
            with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry):
                with override_ap_frontend_settings(BUNDLER=getattr(self, bundler_name)):
                    tpl = Template("{% load bundler %}{% bundler_url 'components/Button.css' %}")
                    actual = tpl.render(Context())
                    self.assertEqual(
                        expected,
                        actual,
                    )

    def test_bundler_embed(self):
        for bundler_name, expected in [
            (
                "test_development_bundler",
                f'<script src="{self.dev_url}components/Button.tsx" type="module"></script>',
            ),
            (
                "test_production_bundler",
                '<script src="/static/assets/Button-def456.js" type="module"></script>\n'
                '<link rel="stylesheet" href="/static/assets/Button-abc123.css">',
            ),
        ]:
            with self.subTest(bundler_name=bundler_name):
                with BundlerAssetContext(
                    frontend_asset_registry=bypass_frontend_asset_registry
                ) as asset_context:
                    with override_ap_frontend_settings(BUNDLER=getattr(self, bundler_name)):
                        tpl = Template(
                            "{% load bundler %}{% bundler_embed 'components/Button.tsx' inline=True %}"
                        )
                        actual = asset_context.post_process(tpl.render(Context()))
                        self.assertEqual(
                            expected,
                            actual,
                        )

    def test_bundler_embed_collected_assets_check(self):
        """Check that bundler_embed_collected_assets exists if it's required by other tags"""
        with override_ap_frontend_settings(
            BUNDLER=self.test_development_bundler,
        ):
            with self.assertRaisesMessage(
                ValueError, "BundlerAssetContext.post_process() was not called but is required"
            ):
                with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry):
                    Template("{% load bundler %}{% bundler_embed 'components/Button.tsx' %}").render(
                        Context()
                    )

            with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry) as asset_context:
                Template("{% load bundler %}{% bundler_embed 'components/Button.tsx' %}").render(Context())
                asset_context.post_process(
                    Template("{% load bundler %}{% bundler_embed_collected_assets %}").render(Context())
                )

    def test_bundler_embed_collected_assets_no_duplicate(self):
        """Check that bundler_embed_collected_assets exists only once"""
        with self.assertRaisesMessage(ValueError, "Duplicate {% bundler_embed_collected_assets %}"):
            with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry):
                Template("{% load bundler %}{% bundler_embed_collected_assets %}").render(Context())
                Template("{% load bundler %}{% bundler_embed_collected_assets %}").render(Context())

    def test_bundler_embed_collected_assets(self):
        for bundler, expected in [
            (
                self.test_development_bundler,
                f'<script src="{self.dev_url}components/Button.tsx" type="module"></script>',
            ),
            (
                self.test_production_bundler,
                '<script src="/static/assets/Button-def456.js" type="module"></script>\n'
                '<link rel="stylesheet" href="/static/assets/Button-abc123.css">',
            ),
        ]:
            with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry) as asset_context:
                with override_ap_frontend_settings(BUNDLER=bundler):
                    context = Context()
                    Template("{% load bundler %}{% bundler_embed 'components/Button.tsx' %}").render(context)
                    tpl = Template("{% load bundler %}{% bundler_embed_collected_assets %}")
                    actual = asset_context.post_process(tpl.render(context))
                    self.assertEqual(
                        expected,
                        actual,
                    )

    def test_bundler_embed_collected_assets_order(self):
        """Test ordering is preserved as it might be important"""
        for bundler_name, expected in [
            (
                "test_development_bundler",
                # yes, in dev css is loaded via <script>
                f'<script src="{self.dev_url}styles/normalize.css" type="module"></script>\n'
                f'<script src="{self.dev_url}components/Button.tsx" type="module"></script>\n'
                f'<script src="{self.dev_url}{resolve_vanilla_extract_cache_names(self.test_development_bundler, "login.css.ts")[1].relative_to(settings.PROJECT_DIR)}" type="module" blocking="render"></script>',
            ),
            (
                "test_production_bundler",
                '<link rel="stylesheet" href="/static/assets/normalize-x1.css">\n'
                '<script src="/static/assets/Button-def456.js" type="module"></script>\n'
                '<link rel="stylesheet" href="/static/assets/Button-abc123.css">\n'
                # While this file is generated ViteCssEmbed specifically excludes it as
                # it knows it's not needed
                # '<script src="/static/assets/login.css-669fd56c.js" type="module"></script>\n'
                '<link rel="stylesheet" href="/static/assets/login.css-a9690449.css">',
            ),
        ]:
            with self.subTest(bundler_name=bundler_name):
                with BundlerAssetContext(
                    frontend_asset_registry=bypass_frontend_asset_registry
                ) as asset_context:
                    with override_ap_frontend_settings(BUNDLER=getattr(self, bundler_name)):
                        context = Context()
                        Template(
                            """
                            {% load bundler %}
                            {% bundler_embed 'styles/normalize.css' %}
                            {% bundler_embed 'components/Button.tsx' %}
                            {% bundler_embed 'login.css.ts' %}
                        """
                        ).render(context)
                        tpl = Template("{% load bundler %}{% bundler_embed_collected_assets %}")
                        actual = asset_context.post_process(tpl.render(context))
                        self.assertEqual(
                            expected,
                            actual,
                        )

    def test_bundler_embed_collected_assets_content_type_css(self):
        for bundler_name, expected in [
            (
                "test_development_bundler",
                # In dev we don't know about any dependencies as everything is loaded by the JS file. As such requesting
                # css will result in no embeds
                "",
            ),
            ("test_production_bundler", '<link rel="stylesheet" href="/static/assets/Button-abc123.css">'),
        ]:
            with self.subTest(bundler_name=bundler_name):
                with BundlerAssetContext(
                    frontend_asset_registry=bypass_frontend_asset_registry
                ) as asset_context:
                    with override_ap_frontend_settings(BUNDLER=getattr(self, bundler_name)):
                        context = Context()
                        Template(
                            "{% load bundler %}{% bundler_embed 'components/Button.tsx' content_type='text/css' %}"
                        ).render(context)
                        tpl = Template("{% load bundler %}{% bundler_embed_collected_assets %}")
                        actual = asset_context.post_process(tpl.render(context))
                        self.assertEqual(
                            expected,
                            actual,
                        )

    def test_bundler_embed_collected_assets_content_type_js(self):
        for bundler_name, expected in [
            (
                "test_development_bundler",
                f'<script src="{self.dev_url}components/Button.tsx" type="module"></script>',
            ),
            (
                "test_production_bundler",
                '<script src="/static/assets/Button-def456.js" type="module"></script>',
            ),
        ]:
            with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry) as asset_context:
                with override_ap_frontend_settings(BUNDLER=getattr(self, bundler_name)):
                    context = Context()
                    Template(
                        "{% load bundler %}{% bundler_embed 'components/Button.tsx' content_type='text/javascript' %}"
                    ).render(context)
                    tpl = Template("{% load bundler %}{% bundler_embed_collected_assets %}")
                    actual = asset_context.post_process(tpl.render(context))
                    self.assertEqual(
                        expected,
                        actual,
                    )

    def test_bundler_embed_collected_assets_css_inline(self):
        for bundler_name, expected in [
            (
                "test_development_bundler",
                # Dev currently doesn't support inline css so will just output script tag
                f'<script src="{self.dev_url}components/Button.tsx" type="module"></script>',
            ),
            (
                "test_production_bundler",
                '<script src="/static/assets/Button-def456.js" type="module"></script>\n'
                f'<style>{inline_css_prod[fixtures_dir / "build_test/assets/Button-abc123.css"]}</style>',
            ),
        ]:
            with self.subTest(bundler_name=bundler_name):
                with BundlerAssetContext(
                    frontend_asset_registry=bypass_frontend_asset_registry,
                    html_target=HtmlGenerationTarget("test", include_scripts=True, inline_css=True),
                ) as asset_context:
                    with override_ap_frontend_settings(BUNDLER=getattr(self, bundler_name)):
                        context = Context()
                        Template("{% load bundler %}{% bundler_embed 'components/Button.tsx' %}").render(
                            context
                        )
                        tpl = Template("{% load bundler %}{% bundler_embed_collected_assets %}")
                        with mock.patch("pathlib.Path.read_text", mock_read_text):
                            actual = asset_context.post_process(tpl.render(context))
                            self.assertEqual(
                                expected,
                                actual,
                            )

    def test_bundler_embed_collected_assets_no_scripts(self):
        for bundler_name, expected in [
            (
                "test_development_bundler",
                "",
            ),
            ("test_production_bundler", '<link rel="stylesheet" href="/static/assets/Button-abc123.css">'),
        ]:
            with BundlerAssetContext(
                frontend_asset_registry=bypass_frontend_asset_registry,
                html_target=HtmlGenerationTarget("test", include_scripts=False, inline_css=False),
            ) as asset_context:
                with override_ap_frontend_settings(BUNDLER=getattr(self, bundler_name)):
                    context = Context()
                    Template("{% load bundler %}{% bundler_embed 'components/Button.tsx' %}").render(context)
                    tpl = Template("{% load bundler %}{% bundler_embed_collected_assets %}")
                    actual = asset_context.post_process(tpl.render(context))
                    self.assertEqual(
                        expected,
                        actual,
                    )


# Set these so resolving css-mappings directories
@override_ap_frontend_settings(CACHE_DIR=fixtures_dir, PRODUCTION_DIR=fixtures_dir)
@mock.patch(
    "alliance_platform.frontend.bundler.vanilla_extract.VanillaExtractClassMapping._create_mapping",
    mock_create_mapping,
)
class TestVanillaExtractTemplateTag(SimpleTestCase):
    def setUp(self) -> None:
        self.test_production_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="production",
        )
        self.test_development_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="development",
        )
        self.dev_url = self.test_development_bundler.dev_server_url

    def test_stylesheet(self):
        for bundler_name, expected in [
            # Resolved from fixtures dir / development-css-mappings
            ("test_development_bundler", "LoginView__abc123"),
            # Resolved from fixtures dir / production-css-mappings
            ("test_production_bundler", "__abc123"),
        ]:
            with BundlerAssetContext(
                frontend_asset_registry=bypass_frontend_asset_registry, skip_checks=True
            ):
                with override_ap_frontend_settings(BUNDLER=getattr(self, bundler_name)):
                    tpl = Template(
                        "{% load vanilla_extract %}"
                        "{% stylesheet 'login.css.ts' as styles %}\n"
                        "{{ styles.LoginView }}"
                    )
                    context = Context()
                    actual = tpl.render(context).split("\n")[-1].strip()
                    self.assertEqual(
                        expected,
                        actual,
                    )


@override_ap_frontend_settings(DEBUG_COMPONENT_OUTPUT=False)
class TestComponentTemplateTagCodeGen(SimpleTestCase):
    def setUp(self) -> None:
        self.test_production_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="production",
        )

        self.test_development_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="development",
        )
        self.dev_url = self.test_development_bundler.dev_server_url

    # TODO: Very open to ideas on how to better test this. This will be rather fragile to any
    # changes to how the JS code is generated.
    def assertCodeEqual(self, expected, actual):
        expected = format_code(expected)
        actual = format_code(actual)
        return self.assertEqual(
            [line.strip() for line in expected.splitlines() if line.strip()],
            [line.strip() for line in actual.splitlines() if line.strip()],
        )

    @override_settings(STATIC_URL="/static/")
    def test_component_simple_render(self):
        for bundler_name, expected in [
            # Resolved from fixtures dir / development-css-mappings
            (
                "test_development_bundler",
                f"""
                    <dj-component data-djid="C1"><!-- ___SSR_PLACEHOLDER_0___ --></dj-component>
                    <script type="module">
                        import {{ createElement, renderComponent }} from '{self.dev_url}frontend/src/renderComponent.tsx';
                        import Button, {{  }} from '{self.dev_url}components/Button.tsx';
                        renderComponent(
                          document.querySelector("[data-djid='C1']"),
                          createElement(Button, {{}}, "Click Me"),
                          "C1",
                          true
                        );
                    </script>
                """,
            ),
            # Resolved from fixtures dir / production-css-mappings
            (
                "test_production_bundler",
                """
                    <dj-component data-djid="C1"><!-- ___SSR_PLACEHOLDER_0___ --></dj-component>
                    <script type="module">
                        import { createElement, renderComponent } from '/static/assets/renderComponent-e1.js';
                        import Button, {  } from '/static/assets/Button-def456.js';
                        renderComponent(
                            document.querySelector("[data-djid='C1']"),
                            createElement(Button, {}, "Click Me"),
                            "C1",
                            true
                        );
                    </script>
                """,
            ),
        ]:
            with mock.patch(
                "alliance_platform.frontend.bundler.middleware.BundlerAssetContext.generate_id"
            ) as mock_method:
                container_id = "C1"
                mock_method.return_value = container_id
                with BundlerAssetContext(
                    frontend_asset_registry=bypass_frontend_asset_registry,
                    skip_checks=True,
                ) as asset_context:
                    with override_ap_frontend_settings(
                        BUNDLER=getattr(self, bundler_name),
                    ):
                        tpl = Template(
                            "{% load react %}"
                            "{% component 'components/Button.tsx' %}Click Me{% endcomponent %}"
                        )
                        context = Context()
                        actual = tpl.render(context)
                        self.assertCodeEqual(expected, actual)
                        self.assertEqual(len(asset_context.ssr_queue), 1)

    def test_component_children(self):
        with override_ap_frontend_settings(
            BUNDLER=self.test_development_bundler,
        ):
            with mock.patch(
                "alliance_platform.frontend.bundler.middleware.BundlerAssetContext.generate_id"
            ) as mock_method:
                container_id = "C1"
                mock_method.return_value = container_id
                with BundlerAssetContext(
                    skip_checks=True, frontend_asset_registry=bypass_frontend_asset_registry
                ) as asset_context:
                    tpl = Template(
                        "{% load react %}"
                        "{% component 'components/Button.tsx' %}Click {% component 'strong' %}Me{% endcomponent %}{% endcomponent %}"
                    )
                    context = Context()
                    actual = tpl.render(context)
                    self.assertCodeEqual(
                        actual,
                        """
                        <dj-component data-djid="C1"><!-- ___SSR_PLACEHOLDER_0___ --></dj-component>
                        <script type="module">
                            import { createElement, renderComponent } from "%sfrontend/src/renderComponent.tsx";
                            import Button from "%scomponents/Button.tsx";

                            renderComponent(
                              document.querySelector("[data-djid='C1']"),
                              createElement(Button, {}, "Click ", createElement("strong", {}, "Me")),
                              "C1",
                              true
                            );
                        </script>
                        """
                        % (
                            self.dev_url,
                            self.dev_url,
                        ),  # used this rather than f-string to avoid escaping curly braces
                    )
                    ssr_context = SSRSerializerContext(self.test_development_bundler)
                    items = json.loads(
                        json.dumps(
                            {
                                placeholder: ssr_item.serialize(ssr_context)
                                for placeholder, ssr_item in asset_context.ssr_queue.items()
                            },
                            ssr_context=ssr_context,
                            cls=SSRJsonEncoder,
                        )
                    )
                    self.assertEqual(len(ssr_context.get_required_imports()), 1)
                    self.assertEqual(len(asset_context.ssr_queue), 1)
                    import_id = next(iter(ssr_context.get_required_imports().keys()))
                    self.assertEqual(
                        items,
                        {
                            "<!-- ___SSR_PLACEHOLDER_0___ -->": {
                                "ssrType": "Component",
                                "payload": {
                                    "component": [
                                        "@@CUSTOM",
                                        "ComponentImport",
                                        {
                                            "import": import_id,
                                            "propertyName": None,
                                        },
                                    ],
                                    "props": {
                                        "children": [
                                            "Click ",
                                            [
                                                "@@CUSTOM",
                                                "Component",
                                                {"component": "strong", "props": {"children": "Me"}},
                                            ],
                                        ]
                                    },
                                    "identifierPrefix": "C1",
                                },
                            }
                        },
                    )

    def test_ssr_disabled(self):
        with override_ap_frontend_settings(
            BUNDLER=self.test_development_bundler,
        ):
            with BundlerAssetContext(
                frontend_asset_registry=bypass_frontend_asset_registry, skip_checks=True
            ) as asset_context:
                tpl = Template(
                    "{% load react %}"
                    "{% component 'components/Button.tsx' ssr:disabled=True %}Click {% component 'strong' %}Me{% endcomponent %}{% endcomponent %}"
                )
                context = Context()
                tpl.render(context)
                self.assertFalse(asset_context.ssr_queue)

    def test_props_dict(self):
        """Tests that props passed through as a dict to `props` kwarg work"""
        with override_ap_frontend_settings(
            BUNDLER=self.test_development_bundler,
        ):
            with BundlerAssetContext(
                frontend_asset_registry=bypass_frontend_asset_registry, skip_checks=True
            ):
                with mock.patch(
                    "alliance_platform.frontend.bundler.middleware.BundlerAssetContext.generate_id"
                ) as mock_method:
                    container_id = "C1"
                    mock_method.return_value = container_id
                    tpl = Template(
                        "{% load react %}"
                        "{% component 'button' disabled=True props=props %}Click{% endcomponent %}"
                    )
                    context = Context(
                        {
                            "props": {
                                "aria-label": "Click Me",
                                "date": datetime.date(2022, 12, 1),
                            }
                        }
                    )
                    actual = tpl.render(context)
                    self.assertIn(
                        """renderComponent(document.querySelector("[data-djid='C1']"), createElement("button", {disabled: true, "aria-label": "Click Me", date: new CalendarDate(2022, 12, 1)}, "Click"), "C1", true)""",
                        actual,
                    )

    def assertSerializedPropsEqual(self, template_contents: str, context: dict, expected_props: dict):
        """Helper to compare props generated for a components

        Args:
            template_contents: Template string to use. Should include 1 {% component %} tag that will have it's
                props extracted
            context: The context to pass to the template. It will be wrapped in ``Context`` for you.
            expected_props: The expected props for the component
        """
        node: ComponentNode = cast(
            ComponentNode, Template(template_contents).compile_nodelist().get_nodes_by_type(ComponentNode)[0]
        )
        props = node.resolve_props(Context(context))
        ssr_context = SSRSerializerContext(self.test_development_bundler)
        props = json.loads(
            json.dumps(props.serialize(ssr_context), cls=SSRJsonEncoder, ssr_context=ssr_context)
        )

        self.assertEqual(expected_props, props)

    def test_deep_nesting(self):
        """Tests that props passed through as a dict to `props` kwarg work"""
        with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry, skip_checks=True):
            self.assertSerializedPropsEqual(
                "{% load react %}"
                "{% component 'button' disabled=True props=props %}Click "
                "{% if True %}{% component 'div' %}Me "
                "{% if True %}{% component 'span' %}Now {% endcomponent %}{% endif %}{% endcomponent %}{% endif %}"
                " Please, "
                "{% component 'strong' %}Thanks!{% endcomponent %}"
                "{% endcomponent %}",
                {
                    "props": {
                        "aria-label": "Click Me",
                    }
                },
                {
                    "disabled": True,
                    "children": [
                        "Click ",
                        [
                            "@@CUSTOM",
                            "Component",
                            {
                                "component": "div",
                                "props": {
                                    "children": [
                                        "Me ",
                                        [
                                            "@@CUSTOM",
                                            "Component",
                                            {
                                                "component": "span",
                                                "props": {"children": "Now "},
                                            },
                                        ],
                                    ],
                                },
                            },
                        ],
                        " Please, ",
                        [
                            "@@CUSTOM",
                            "Component",
                            {
                                "component": "strong",
                                "props": {"children": "Thanks!"},
                            },
                        ],
                    ],
                    "aria-label": "Click Me",
                },
            )

    def test_date_prop(self):
        with override_ap_frontend_settings(
            BUNDLER=self.test_development_bundler,
        ):
            with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry):
                self.assertSerializedPropsEqual(
                    "{% load react %}" "{% component 'DatePicker' date=date %}{% endcomponent %}",
                    {
                        "date": datetime.date(2022, 12, 1),
                    },
                    {"date": ["@@CUSTOM", "Date", [2022, 12, 1]]},
                )

                self.assertSerializedPropsEqual(
                    "{% load react %}" "{% component 'DateTimePicker' datetime=datetime %}{% endcomponent %}",
                    {
                        "datetime": datetime.datetime(2022, 12, 1, 12, 10, 10, 0),
                    },
                    {"datetime": ["@@CUSTOM", "DateTime", [2022, 12, 1, 12, 10, 10, 0]]},
                )

                self.assertSerializedPropsEqual(
                    "{% load react %}" "{% component 'DateTimePicker' datetime=datetime %}{% endcomponent %}",
                    {
                        "datetime": make_aware(datetime.datetime(2022, 12, 1, 12, 10, 10, 0)),
                    },
                    {
                        "datetime": [
                            "@@CUSTOM",
                            "ZonedDateTime",
                            [2022, 12, 1, "Australia/Melbourne", 39600000, 12, 10, 10, 0],
                        ]
                    },
                )

    def test_time_prop(self):
        with override_ap_frontend_settings(
            BUNDLER=self.test_development_bundler,
        ):
            with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry):
                self.assertSerializedPropsEqual(
                    "{% load react %}" "{% component 'Time' time=time %}{% endcomponent %}",
                    {
                        "time": datetime.time(12, 30, 15, 5),
                    },
                    {
                        "time": [
                            "@@CUSTOM",
                            "Time",
                            [12, 30, 15, 5],
                        ]
                    },
                )

    def test_whitespace_handling(self):
        with override_ap_frontend_settings(BUNDLER=self.test_development_bundler):
            with mock.patch(
                "alliance_platform.frontend.bundler.middleware.BundlerAssetContext.generate_id"
            ) as mock_method:
                container_id = "C1"
                mock_method.return_value = container_id
                with BundlerAssetContext(
                    skip_checks=True, frontend_asset_registry=bypass_frontend_asset_registry
                ):
                    tpl_str = """
                        {% load react %}
                        {% component 'components/Button.tsx' %}

                            Click {% component 'strong' %} Me  {% endcomponent %}
                            Ok
                                then
Some               space
   {% component 'b' %}Test
         {{ ok }} {{ num }}   {% endcomponent %}
                        {% endcomponent %}"
                    """
                    self.assertSerializedPropsEqual(
                        tpl_str,
                        {"ok": True, "num": 5},
                        {
                            "children": [
                                "Click ",
                                [
                                    "@@CUSTOM",
                                    "Component",
                                    {"component": "strong", "props": {"children": " Me  "}},
                                ],
                                "Ok then Some               space",
                                [
                                    "@@CUSTOM",
                                    "Component",
                                    {"component": "b", "props": {"children": "Test True 5   "}},
                                ],
                            ]
                        },
                    )


test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


@override_ap_frontend_settings(
    # We rely on this in _get_debug_tree
    DEBUG_COMPONENT_OUTPUT=True,
    BUNDLER=test_development_bundler,
)
class TestComponentTemplateTagOutput(SimpleTestCase):
    """For ease of testing, these tests just use the pretty debug output for comparing code

    For testing the actual codegen itself, see the above tests
    """

    def setUp(self):
        self.bundler_context = BundlerAssetContext(
            frontend_asset_registry=bypass_frontend_asset_registry, skip_checks=True
        )
        self.bundler_context.__enter__()

    def tearDown(self):
        self.bundler_context.__exit__(None, None, None)

    def _get_debug_tree(self, template_contents: str, **kwargs: dict):
        def patch_debug_tree(self, props: ComponentProps, include_template_origin=True):
            # Like the default implementation except we never include template origin string
            printer = TypescriptPrinter(jsx_transform=None)
            generator = ComponentSourceCodeGenerator(self)
            jsx_element = generator.create_jsx_element_node(self, props, False)
            return printer.print(jsx_element)

        with mock.patch(
            "alliance_platform.frontend.templatetags.react.ComponentNode.print_debug_tree", patch_debug_tree
        ):
            template = Template("{% load react %}" + template_contents)
            context = Context(kwargs)
            context.template = template
            contents = template.render(context)
            code = contents.split("<!--").pop().split("-->").pop(0)
            return code.strip()

    def assertComponentEqual(self, template_code, expected_output, **kwargs):
        self.assertEqual(
            run_prettier(self._get_debug_tree(template_code, **kwargs)),
            run_prettier(expected_output),
        )

    def test_django_lazy_object_as_prop(self):
        def get_token():
            return "abc123"

        token = lazy(get_token, str)
        self.assertComponentEqual(
            """{% component "CustomForm" csrf_token=csrf_token %}{% endcomponent %}""",
            """
            <CustomForm csrfToken="abc123" />
            """,
            csrf_token=token,
        )

    def test_django_simple_lazy_object_as_prop(self):
        def get_token():
            return "abc123"

        token = SimpleLazyObject(get_token)
        self.assertComponentEqual(
            """{% component "CustomForm" csrf_token=csrf_token %}{% endcomponent %}""",
            """
            <CustomForm csrfToken="abc123" />
            """,
            csrf_token=token,
        )

    def test_variable_string_concat(self):
        self.assertComponentEqual(
            """{% component "Button" %}Hello {{ name }}{% endcomponent %}""",
            """
            <Button>
              Hello Sam
            </Button>
            """,
            name="Sam",
        )

    def test_boolean_attribute(self):
        self.assertComponentEqual(
            """{% component "Button" is_disabled=True %}Disabled{% endcomponent %}""",
            """<Button isDisabled={true}>Disabled</Button>""",
        )

    def test_string_attribute(self):
        self.assertComponentEqual(
            """{% component "Button" variant="primary" %}Click Me{% endcomponent %}""",
            """<Button variant="primary">Click Me</Button>""",
        )

    def test_numeric_attribute(self):
        self.assertComponentEqual(
            """{% component "Range" min_value=5  %}{% endcomponent %}""",
            """<Range minValue={5} />""",
        )

    def test_variable_attribute(self):
        self.assertComponentEqual(
            """{% component "Button" variant=variant %}Click Me{% endcomponent %}""",
            """<Button variant="secondary">Click Me</Button>""",
            variant="secondary",
        )

    def test_variable_attribute_raw_html(self):
        self.assertComponentEqual(
            """{% component "Button" %}Click <strong id="test-{{id}}">Me</strong>{% endcomponent %}""",
            """<Button>Click <strong id="test-secondary">Me</strong></Button>""",
            id="secondary",
        )

    def test_special_attribute(self):
        self.assertComponentEqual(
            """{% component "Button" aria-label="Disable" %}X{% endcomponent %}""",
            """<Button aria-label="Disable">X</Button>""",
        )

    def test_html_entities(self):
        self.assertComponentEqual(
            """{% component "Button" %}&ldquo;Testing and Stuff&rdquo;{% endcomponent %}""",
            """<Button>“Testing and Stuff”</Button>""",
        )

    def test_nested_component(self):
        self.assertComponentEqual(
            """{% component "Button" %}Welcome {% component "strong" %}{{ name }}{% endcomponent %}{% endcomponent %}""",
            """<Button>Welcome <strong>Sam</strong></Button>""",
            name="Sam",
        )

    def test_nested_component_raw_html(self):
        self.assertComponentEqual(
            """{% component "Button" %}Welcome <strong>{{ name }}</strong>{% endcomponent %}""",
            """
            <Button>Welcome <strong>Sam</strong></Button>
            """,
            name="Sam",
        )

    def test_nested_component_raw_html_from_include(self):
        self.assertComponentEqual(
            """{% component "Button" %}Welcome {% include "react_test_templates/nested_raw_tag.html" with name=name %}{% endcomponent %}""",
            """
            <Button>Welcome <strong>Sam</strong></Button>
            """,
            name="Sam",
        )

    def test_nested_component_from_include(self):
        self.assertComponentEqual(
            """{% component "Button" %}Welcome {% include "react_test_templates/nested_tag.html" with name=name %}{% endcomponent %}""",
            """
            <Button>Welcome <strong>Sam</strong></Button>
            """,
            name="Sam",
        )

    def test_template_include(self):
        self.assertComponentEqual(
            """{% component "Button" %}Hello {% include "react_test_templates/simple_include.html" %}{% endcomponent %}""",
            """
            <Button>
              Hello Inner Content
            </Button>
            """,
            name="Sam",
        )

    def test_pass_component_as_prop(self):
        self.assertComponentEqual(
            """
            {% component "Icon" as icon %}{% endcomponent %}
            {% component "Button" icon=icon %}Click{% endcomponent %}""",
            """<Button icon={<Icon />}>Click</Button>""",
            name="Sam",
        )

    def test_html_in_var(self):
        self.assertComponentEqual(
            """
            {% component "div" %}{{ text }}{% endcomponent %}""",
            """<div><strong>Should not be escaped</strong></div>""",
            text=mark_safe("<strong>Should not be escaped</strong>"),
        )

        self.assertComponentEqual(
            """
            {% component "div" %}{{ text }}{% endcomponent %}""",
            """<div>{'<strong>Should be escaped</strong>'}</div>""",
            text="<strong>Should be escaped</strong>",
        )

    def test_html_in_var_nested(self):
        self.assertComponentEqual(
            """
            {% component "div" %}{{ text }}{% endcomponent %}""",
            """<div><strong>Should not be <i>escaped</i></strong></div>""",
            text=mark_safe("<strong>Should not be <i>escaped</i></strong>"),
        )
