from contextlib import contextmanager
from typing import cast

from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.ui.forms.renderers import form_input_context_key
from allianceutils.auth.permission import AmbiguousGlobalPermissionWarning
from allianceutils.tests.util import warning_filter
from django import forms
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from test_alliance_platform_ui.factory import UserFactory
from test_alliance_platform_ui.models import User

from .test_utils import override_ap_frontend_settings
from .test_utils.bundler import TestViteBundler
from .test_utils.bundler import bundler_kwargs
from .test_utils.bundler import bypass_frontend_asset_registry


class TestForm(forms.Form):
    first_name = forms.CharField(label="First name", max_length=100)
    second_name = forms.CharField(label="Last name", max_length=100)


@override_ap_frontend_settings(
    DEBUG_COMPONENT_OUTPUT=False,
)
@override_settings(ROOT_URLCONF="test_alliance_platform_ui.urls")
@warning_filter("ignore", category=AmbiguousGlobalPermissionWarning)
class FormRenderingTestCase(TestCase):
    PERM = "test_utils.link_is_allowed"

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
                    UserWarning, msg="form_input tag should only be used with 'FormInputContextRenderer'"
                ):
                    self.client.get(reverse("update_user", kwargs={"pk": user.pk}), follow=True)

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
