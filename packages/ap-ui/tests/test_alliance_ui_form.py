from contextlib import contextmanager
from typing import cast
from unittest import mock

from alliance_platform.codegen.printer import TypescriptPrinter
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.frontend.templatetags.react import ComponentProps
from alliance_platform.frontend.templatetags.react import ComponentSourceCodeGenerator
from alliance_platform.ui.forms.renderers import form_input_context_key
from allianceutils.auth.permission import AmbiguousGlobalPermissionWarning
from allianceutils.tests.util import warning_filter
from django import forms
from django.template import Context
from django.template import Template
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from test_alliance_platform_ui.factory import UserFactory
from test_alliance_platform_ui.models import User

from .test_utils import override_ap_frontend_settings
from .test_utils.bundler import TestViteBundler
from .test_utils.bundler import bundler_kwargs
from .test_utils.bundler import bypass_frontend_asset_registry
from .test_utils.bundler import run_prettier


class TestForm(forms.Form):
    first_name = forms.CharField(label="First name", max_length=100)
    second_name = forms.CharField(label="Last name", max_length=100)


test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


@override_ap_frontend_settings(
    # We rely on this in _get_debug_tree
    DEBUG_COMPONENT_OUTPUT=True,
    BUNDLER=test_development_bundler,
)
@override_settings(ROOT_URLCONF="test_alliance_platform_ui.urls")
@warning_filter("ignore", category=AmbiguousGlobalPermissionWarning)
class FormRenderingTestCase(TestCase):
    PERM = "test_utils.link_is_allowed"

    def setUp(self) -> None:
        self.bundler_context = BundlerAssetContext(
            frontend_asset_registry=bypass_frontend_asset_registry, skip_checks=True
        )
        self.bundler_context.__enter__()
        self.test_production_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="production",
        )

        self.test_development_bundler = TestViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="development",
        )
        self.dev_url = self.test_development_bundler.dev_server_url

    def tearDown(self):
        self.bundler_context.__exit__(None, None, None)

    def _get_debug_tree(self, template_contents: str, **kwargs: dict):
        def patch_debug_tree(self, props: ComponentProps, include_template_origin=True):
            # Like the default implementation except we never include template origin string
            printer = TypescriptPrinter(jsx_transform=None, codegen_target="file")
            generator = ComponentSourceCodeGenerator(self)
            jsx_element = generator.create_jsx_element_node(self, props, False)
            return printer.print(jsx_element)

        with mock.patch(
            "alliance_platform.frontend.templatetags.react.ComponentNode.print_debug_tree",
            patch_debug_tree,
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

    def get_user(self) -> User:
        user = cast(User, UserFactory(is_superuser=True))
        return user

    @contextmanager
    def setup_overrides(self):
        with override_ap_frontend_settings(BUNDLER=self.test_development_bundler):
            with BundlerAssetContext(
                skip_checks=True, frontend_asset_registry=bypass_frontend_asset_registry
            ):
                yield

    def test_form_input_requires_renderer(self):
        user = self.get_user()

        with self.setup_overrides():
            with override_settings(FORM_RENDERER="django.forms.renderers.DjangoTemplates"):
                with self.assertWarns(
                    UserWarning,
                    msg="form_input tag should only be used with 'FormInputContextRenderer'",
                ):
                    self.client.get(reverse("update_user", kwargs={"pk": user.pk}), follow=True)

        # IMPORTANT: Clear the form renderer cache after overriding settings
        # Django 4.2+ caches the renderer with @lru_cache which persists across tests
        from django.forms.renderers import get_default_renderer

        get_default_renderer.cache_clear()

    def test_renderer_handles_context_key(self):
        user = self.get_user()
        response = self.client.get(reverse("update_user", kwargs={"pk": user.pk}), follow=True)
        for context_value in response.context:
            context_dict = context_value.dicts[1]
            if "widget" in context_dict and "attrs" in context_dict["widget"]:
                # check that context key is removed from widget attrs
                self.assertFalse(form_input_context_key in context_dict["widget"]["attrs"])
                # check that context information has been added to top level context
                self.assertTrue("extra_widget_props" in context_dict)

    def test_html_form_nested_components(self):
        """Test that everything in a {% form %} tag is rendered as expected when nested within a component"""
        self.assertComponentEqual(
            """
            {% load react %}
            {% load alliance_platform.form %}
            {% component "div" %}{% form my_form %} <form> {% component "input" %}{% endcomponent %}  </form> {% endform %}{% endcomponent %}""",
            """<div><form><input /></form></div>""",
            my_form=TestForm(),
        )

        self.assertComponentEqual(
            """
            {% load react %}
            {% load alliance_platform.form %}
            {% component "div" %}{% if 1 %} <form> {% component "input" %}{% endcomponent %} {% component "span" %}{% endcomponent %} </form> {% endif %}{% endcomponent %}""",
            """<div><form><input /><span /></form></div>""",
            my_form=TestForm(),
        )

        self.assertComponentEqual(
            """
            {% load react %}
            {% load alliance_platform.form %}
            {% component "div" %}{% if 0 %} <form> {% component "input" %}{% endcomponent %} {% component "span" %}{% endcomponent %} </form> {% endif %}{% endcomponent %}""",
            """<div />""",
            my_form=TestForm(),
        )
