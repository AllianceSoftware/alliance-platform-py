from contextlib import contextmanager
from typing import cast

from django.contrib.sessions.backends.base import SessionBase
from django.contrib.auth.models import PermissionsMixin
from django.http import HttpRequest
from django.template import Context
from django.template import Template
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from factory import Faker
from factory.django import DjangoModelFactory

from ...bundler.context import BundlerAssetContext
from .test_bundler_templatetags import bundler_kwargs
from .test_bundler_templatetags import bypass_frontend_asset_registry
from .test_bundler_templatetags import TestViteBundler
from allianceutils.auth.permission import AmbiguousGlobalPermissionWarning

from allianceutils.auth.models import GenericUserProfile
from allianceutils.tests.util import warning_filter


class TestUser(GenericUserProfile, PermissionsMixin):
    pass

    class Meta:
        abstract = False


class UserFactory(DjangoModelFactory):
    first_name: Faker[str, str] = Faker("first_name")
    last_name: Faker[str, str] = Faker("last_name")
    email: Faker[str, str] = Faker(
        "email", domain="example.com"
    )  # reserved by IANA, sending email to these addresses wont hit
    is_superuser = False

    class Meta:
        model = TestUser


@override_settings(
    FRONTEND_DEBUG_COMPONENT_OUTPUT=False,
    AUTHENTICATION_BACKENDS=(
        # This uses alliance_django_frontend.test_utils.rules. This works with reverse_if_probably_allowed as it
        # will correctly infer object level permissions without us needing to setup a custom csv permissions
        # for the test cases
        "rules.permissions.ObjectPermissionBackend",
    ),
)
@override_settings(ROOT_URLCONF="alliance_django_frontend.test_utils.urls")
@warning_filter("ignore", category=AmbiguousGlobalPermissionWarning)
class UrlFilterPermTemplateTagsTestCase(TestCase):
    PERM = "test_utils.link_is_allowed"
    GLOBAL_PERM_URL = "url_with_perm_global"
    OBJECT_PERM_URL = "url_with_perm_object"
    MULTIPLE_ARGS_URL = "url_with_multiple_args"

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

    def get_privileged_user(self) -> TestUser:
        user = cast(TestUser, UserFactory(is_superuser=True))
        self.assertTrue(user.has_perm(self.PERM))
        return user

    def get_unprivileged_user(self) -> TestUser:
        user = cast(TestUser, UserFactory(is_superuser=False))
        self.assertFalse(user.has_perm(self.PERM))
        return user

    @contextmanager
    def setup_overrides(self):
        with override_settings(FRONTEND_BUNDLER=self.test_development_bundler):
            with BundlerAssetContext(
                skip_checks=True, frontend_asset_registry=bypass_frontend_asset_registry
            ):
                yield

    def test_global_url_with_perm(self):
        user1 = self.get_privileged_user()
        user2 = self.get_unprivileged_user()

        with self.setup_overrides():
            tpl = Template(
                """
            {% load react %}
            {% load alliance_ui %}
            {% component "a" href=perm|url_with_perm %}{% endcomponent %}
            """
            )
            request = HttpRequest()
            request.user = user2
            request.session = SessionBase()
            context = Context({"request": request, "perm": self.GLOBAL_PERM_URL})
            output = tpl.render(context)
            self.assertEqual(output.strip(), "")
            request.user = user1
            output = tpl.render(context)
            url = reverse(self.GLOBAL_PERM_URL)
            self.assertTrue(f'href: "{url}"' in output)

    def test_object_url_with_perm(self):
        user1 = self.get_privileged_user()
        user2 = self.get_unprivileged_user()

        with self.setup_overrides():
            tpl = Template(
                """
            {% load react %}
            {% load alliance_ui %}
            {% component "a" href=perm|url_with_perm:user.pk|with_perm_obj:user %}{% endcomponent %}
            """
            )

            request = HttpRequest()
            request.user = user2
            request.session = SessionBase()
            context = Context({"request": request, "user": user1, "perm": self.OBJECT_PERM_URL})
            output = tpl.render(context)
            self.assertEqual(output.strip(), "")
            request.user = user1
            output = tpl.render(context)
            url = reverse(self.OBJECT_PERM_URL, args=[user1.pk])
            self.assertTrue(f'href: "{url}"' in output)

    def test_object_url_with_perm_with_kwargs(self):
        user1 = self.get_privileged_user()
        user2 = self.get_unprivileged_user()

        with self.setup_overrides():
            tpl = Template(
                """
            {% load react %}
            {% load alliance_ui %}
            {% component "a" href=perm|url_with_perm|with_kwargs:kwargs %}{% endcomponent %}
            """
            )

            request = HttpRequest()
            request.user = user2
            request.session = SessionBase()
            context = Context(
                {
                    "request": request,
                    "kwargs": {"pk": user1.pk},
                    "perm": self.OBJECT_PERM_URL,
                    "user": user1.pk,
                }
            )
            output = tpl.render(context)
            self.assertEqual(output.strip(), "")
            request.user = user1
            with self.assertNumQueries(1):
                # We expect 1 query to lookup the object
                output = tpl.render(context)
                url = reverse(self.OBJECT_PERM_URL, args=[user1.pk])
                self.assertTrue(f'href: "{url}"' in output)

            with self.assertNumQueries(0):
                # If we pass the object then there should be no query
                tpl = Template(
                    """
                {% load react %}
                {% load alliance_ui %}
                {% component "a" href=perm|url_with_perm|with_kwargs:kwargs|with_perm_obj:user %}{% endcomponent %}
                """
                )
                output = tpl.render(context)
                url = reverse(self.OBJECT_PERM_URL, args=[user1.pk])
                self.assertTrue(f'href: "{url}"' in output)

    def test_with_arg(self):
        user1 = self.get_privileged_user()
        user2 = self.get_unprivileged_user()

        with self.setup_overrides():
            tpl = Template(
                """
            {% load react %}
            {% load alliance_ui %}
            {% component "a" href=perm|url_with_perm:user.pk|with_arg:2|with_arg:"abc123"|with_perm_obj:user %}{% endcomponent %}
            """
            )

            request = HttpRequest()
            request.user = user2
            request.session = SessionBase()
            context = Context({"request": request, "user": user1, "perm": self.MULTIPLE_ARGS_URL})
            output = tpl.render(context)
            self.assertEqual(output.strip(), "")
            request.user = user1
            output = tpl.render(context)
            url = reverse(self.MULTIPLE_ARGS_URL, args=[user1.pk, 2, "abc123"])
            self.assertTrue(f'href: "{url}"' in output)

    def test_url_no_perm_check(self):
        user1 = self.get_privileged_user()
        user2 = self.get_unprivileged_user()

        with self.setup_overrides():
            tpl = Template(
                """
            {% load react %}
            {% load alliance_ui %}
            {% component "a" href=perm|url:user.pk|with_arg:2|with_arg:"abc123" %}{% endcomponent %}
            """
            )

            request = HttpRequest()
            request.user = user2
            request.session = SessionBase()
            context = Context({"request": request, "user": user1, "perm": self.MULTIPLE_ARGS_URL})
            output = tpl.render(context)
            url = reverse(self.MULTIPLE_ARGS_URL, args=[user1.pk, 2, "abc123"])
            self.assertTrue(f'href: "{url}"' in output)
