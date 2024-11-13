from pathlib import Path
from unittest import skip
from unittest.mock import patch

from alliance_platform.audit import create_audit_event
from alliance_platform.audit import create_audit_model_base
from alliance_platform.audit.registry import AuditRegistry
from alliance_platform.audit.registry import _registration_by_model
from alliance_platform.audit.search import search_audit_by_context
from alliance_platform.audit.templatetags.alliance_platform.audit import AuditListNode
from alliance_platform.frontend.bundler.asset_registry import FrontendAssetRegistry
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from allianceutils.util import camelize
from django.db import models
from django.http import HttpRequest
from django.template import Template
from django.test import Client
from django.test import TestCase
from django.test import modify_settings
from django.test import override_settings
from django.urls import reverse
from test_alliance_platform_audit.factory import AppPaymentMethodFactory
from test_alliance_platform_audit.factory import AppPlazaFactory
from test_alliance_platform_audit.factory import AppShopFactory
from test_alliance_platform_audit.factory import AuthorProfileFactory
from test_alliance_platform_audit.factory import MemberProfileFactory
from test_alliance_platform_audit.factory import ProfileFactory
from test_alliance_platform_audit.factory import SuperMemberProfileFactory
from test_alliance_platform_audit.factory import UserFactory
from test_alliance_platform_audit.models import AuthorProfile
from test_alliance_platform_audit.models import MemberProfile
from test_alliance_platform_audit.models import PaymentMethod
from test_alliance_platform_audit.models import Plaza
from test_alliance_platform_audit.models import Profile
from test_alliance_platform_audit.models import Shop
from test_alliance_platform_audit.models import SuperMemberProfile
from test_alliance_platform_audit.models import User
from test_alliance_platform_audit.models import test_audit_registry


def get_audit_list_props(context, **kwargs):
    # just inspecting props rather than properly rendering the template because
    # the actual component currently only exists in the template project
    arg_str = " ".join([f"{k}={k}" for k in kwargs.keys()])
    nodes = Template(
        f"""
    {{% load alliance_platform.audit %}}
    {{% render_audit_list {arg_str} %}}
    """
    ).compile_nodelist()
    for node in nodes:
        if isinstance(node, AuditListNode):
            return camelize(node.resolve_props({**kwargs, **context}).props)
    raise ValueError("expected AuditListNode")


class TestFrontendAssetRegistryByPass(FrontendAssetRegistry):
    """Bypasses unknown checks by never returning any unknown paths"""

    def get_unknown(self, *filenames: Path) -> list[Path]:
        return []


bypass_frontend_asset_registry = TestFrontendAssetRegistryByPass()


@override_settings(ROOT_URLCONF="test_alliance_platform_audit.urls")
@modify_settings(
    INSTALLED_APPS={"remove": ["silk"]},
    MIDDLEWARE={"remove": ["silk.middleware.SilkyMiddleware"]},
)
class TestAuditModule(TestCase):
    def test_vanilla_create(self):
        method = AppPaymentMethodFactory(name="Visa")
        PaymentMethod.AuditEvent
        self.assertEqual(method.auditevents.count(), 1)
        self.assertEqual(method.auditevents.latest("pgh_id").pgh_label, "CREATE")
        self.assertEqual(method.auditevents.latest("pgh_id").name, "Visa")

    def test_vanilla_update(self):
        method = AppPaymentMethodFactory(name="Visa")
        method.name = "Master"
        method.save()
        self.assertEqual(method.auditevents.count(), 2)
        self.assertEqual(method.auditevents.latest("pgh_id").pgh_label, "UPDATE")
        self.assertEqual(method.auditevents.latest("pgh_id").name, "Master")

    def test_vanilla_delete(self):
        method = AppPaymentMethodFactory(name="Visa")
        method.name = "Master"
        method.save()
        mid = method.id
        method.delete()

        event = PaymentMethod.AuditEvent.objects.filter(pgh_obj_id=mid)

        self.assertEqual(event.count(), 3)
        self.assertEqual(event.latest("pgh_id").pgh_label, "DELETE")
        self.assertEqual(event.latest("pgh_id").name, "Master")

    def test_saving_without_changes_does_not_trigger_audit(self):
        method = AppPaymentMethodFactory(name="Visa")
        method.save()
        method.save()
        method.save()
        method.save()
        method.save()
        self.assertEqual(method.auditevents.count(), 1)

    def test_normal_foreign_key(self):
        plaza1 = AppPlazaFactory(name="Blackburn Mall")
        shop1 = AppShopFactory(name="Shelley's Seafood", plaza=plaza1)
        self.assertEqual(shop1.auditevents.latest("pgh_id").plaza, plaza1)

    def test_foreign_key_delete_cascade_gets_logged(self):
        plaza1 = AppPlazaFactory(name="Blackburn Mall")
        shop1 = AppShopFactory(name="Shelley's Seafood", plaza=plaza1)
        sid = shop1.id
        plaza1.delete()
        event = Shop.AuditEvent.objects.filter(pgh_obj_id=sid)
        self.assertEqual(event.count(), 2)
        self.assertEqual(event.latest("pgh_id").pgh_label, "DELETE")

    def test_context_middleware(self):
        client = Client()
        user = UserFactory.create()
        client.force_login(user)
        url = reverse("test_audit_create_plaza")
        client.post(path=url)
        event = Plaza.AuditEvent.objects.latest("id")
        self.assertEqual(event.pgh_context.metadata, {"url": url, "user": user.id})

    def test_context_middleware_with_additional_context(self):
        client = Client()
        user = UserFactory.create()
        client.force_login(user)
        url = reverse("test_audit_create_plaza_with_context")
        client.post(path=url)
        event = Plaza.AuditEvent.objects.latest("id")
        self.assertEqual(event.pgh_context.metadata, {"url": url, "user": user.id, "pet": "banana"})

    def test_many_to_many_add(self):
        m1 = AppPaymentMethodFactory(name="Visa")
        m2 = AppPaymentMethodFactory(name="Master")
        m3 = AppPaymentMethodFactory(name="Potcoin")
        plaza = AppPlazaFactory(name="Parliament House")
        shop = AppShopFactory(name="Hobgoblin Firecrackers", plaza=plaza)
        shop.payment_methods_accepted.add(m1)
        self.assertEqual(shop.auditevents.latest("pgh_id").payment_methods_accepted, [m1.id])
        self.assertEqual(shop.auditevents.latest("pgh_id").pgh_label, "UPDATE")
        shop.payment_methods_accepted.add(m2, m3)
        self.assertCountEqual(
            shop.auditevents.latest("pgh_id").payment_methods_accepted,
            [m1.id, m2.id, m3.id],
        )

    def test_many_to_many_remove(self):
        m1 = AppPaymentMethodFactory(name="Visa")
        m2 = AppPaymentMethodFactory(name="Master")
        m3 = AppPaymentMethodFactory(name="Potcoin")
        plaza = AppPlazaFactory(name="Parliament House")
        shop = AppShopFactory(name="Hobgoblin Firecrackers", plaza=plaza)
        shop.payment_methods_accepted.add(m1)
        shop.payment_methods_accepted.add(m2, m3)
        shop.payment_methods_accepted.remove(m2)
        self.assertCountEqual(shop.auditevents.latest("pgh_id").payment_methods_accepted, [m1.id, m3.id])
        self.assertEqual(shop.auditevents.latest("pgh_id").pgh_label, "UPDATE")
        shop.payment_methods_accepted.remove(m1, m3)
        self.assertEqual(shop.auditevents.latest("pgh_id").payment_methods_accepted, None)

    def test_many_to_many_set(self):
        m1 = AppPaymentMethodFactory(name="Visa")
        m2 = AppPaymentMethodFactory(name="Master")
        m3 = AppPaymentMethodFactory(name="Potcoin")
        plaza = AppPlazaFactory(name="Parliament House")
        shop = AppShopFactory(name="Hobgoblin Firecrackers", plaza=plaza)
        shop.payment_methods_accepted.set([m1])
        self.assertEqual(shop.auditevents.latest("pgh_id").payment_methods_accepted, [m1.id])
        self.assertEqual(shop.auditevents.latest("pgh_id").pgh_label, "UPDATE")
        shop.payment_methods_accepted.set([m2, m3])
        self.assertCountEqual(shop.auditevents.latest("pgh_id").payment_methods_accepted, [m2.id, m3.id])

    def test_many_to_many_gets_carried_over_on_normal_updates(self):
        m1 = AppPaymentMethodFactory(name="Visa")
        plaza = AppPlazaFactory(name="Parliament House")
        shop = AppShopFactory(name="Hobgoblin Firecrackers", plaza=plaza)
        self.assertEqual(shop.auditevents.latest("pgh_id").payment_methods_accepted, None)
        shop.payment_methods_accepted.add(m1)
        self.assertEqual(shop.auditevents.latest("pgh_id").payment_methods_accepted, [m1.id])
        shop.name = "Hobgoblin goblinfires"
        shop.save()
        self.assertEqual(shop.auditevents.latest("pgh_id").name, "Hobgoblin goblinfires")
        self.assertEqual(shop.auditevents.latest("pgh_id").payment_methods_accepted, [m1.id])

    def test_long_trigger_name(self):
        from pgtrigger import core

        name_too_long = Shop._meta.db_table + "_payment_methods_accepted_m2m_remove"
        self.assertGreater(len(name_too_long), 43)

        name_normal = Shop._meta.db_table + "_insert"
        self.assertLessEqual(len(name_normal), 43)

        found_long_name, found_normal_name = False, False

        for model, trigger in core.registry.registered():
            uri = trigger.get_uri(model)
            if name_normal in uri:
                found_normal_name = True
            if name_too_long in uri:
                found_long_name = True

        self.assertFalse(found_long_name)
        self.assertTrue(found_normal_name)

    def test_custom_events_fail_for_unregistered(self):
        plaza = AppPlazaFactory(name="Parliament House")
        self.assertRaises(ValueError, create_audit_event, plaza, "Built")

    def test_custom_events(self):
        plaza = AppPlazaFactory(name="Parliament House")
        create_audit_event(plaza, "STORMED")
        self.assertEqual(plaza.auditevents.latest("pgh_id").pgh_label, "STORMED")

    def test_search_audit_by_context(self):
        client = Client()
        user = UserFactory.create()
        client.force_login(user)
        url = reverse("test_audit_create_plaza_with_context")
        client.post(path=url)
        url = reverse("test_audit_create_plaza")
        client.post(path=url)
        result = search_audit_by_context({"user": user.id})
        self.assertEqual(len(result[Plaza]), 2)
        result = search_audit_by_context({"pet": "banana"})
        self.assertEqual(len(result[Plaza]), 1)

    def test_audit_permission(self):
        url = reverse("test_audit_log_view")
        plaza_hash = test_audit_registry.hash_model(Plaza)
        shop_hash = test_audit_registry.hash_model(Shop)

        # can audit shop but not plaza

        user = User.objects.create(username="test")
        client = self.client

        self.assertTrue(user.has_perm("test_alliance_platform_audit.shop_audit"))
        self.assertFalse(user.has_perm("test_alliance_platform_audit.plaza_audit"))

        client.force_login(user)

        with self.assertLogs("django.request", "WARNING"):
            response = client.get(f"{url}?model={shop_hash}")
            self.assertEqual(response.status_code, 200)
            response = client.get(f"{url}?model={plaza_hash}")
            self.assertEqual(response.status_code, 403)
            # if user has access to no audits, can't access "all"
            with patch(
                "test_alliance_platform_audit.auth.backends.AuditBackend.has_audit_perm", return_value=False
            ):
                response = client.get(f"{url}?model=all")
                self.assertEqual(response.status_code, 403)

        # triggers a creation of one shop & one plaza in db
        client.post(path=reverse("test_audit_create_shop"))

        # since user has access to at least one audit, should be able to access "all"
        response = client.get(f"{url}?model=all")
        self.assertEqual(response.status_code, 200)

        # additionally, when querying "all", the result from shop should be returned
        # but not the one for plaza
        r = response.json()
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["results"][0]["modelLabel"], "Shop")

    def test_global_audit_permission(self):
        url = reverse("test_audit_log_view")
        plaza_hash = test_audit_registry.hash_model(Plaza)
        shop_hash = test_audit_registry.hash_model(Shop)

        client = self.client
        user = User.objects.create(username="test")

        with patch("test_alliance_platform_audit.auth.backends.global_audit_enabled", return_value=False):
            self.assertTrue(user.has_perm("test_alliance_platform_audit.shop_audit"))
            self.assertFalse(user.has_perm("test_alliance_platform_audit.plaza_audit"))

            # global audit permission turned off, so 403 on all audit listings
            client.force_login(user)

            # triggers a creation of one shop & one plaza in db
            client.post(path=reverse("test_audit_create_shop"))

            with self.assertLogs("django.request", "WARNING"):
                response = client.get(f"{url}?model={plaza_hash}")
                self.assertEqual(response.status_code, 403)

            with self.assertLogs("django.request", "WARNING"):
                response = client.get(f"{url}?model={shop_hash}")
                self.assertEqual(response.status_code, 403)

            with self.assertLogs("django.request", "WARNING"):
                response = client.get(f"{url}?model=all")
                self.assertEqual(response.status_code, 403)

    @skip(
        "test_custom_audit_list_perm_action - how to test this, since permissions "
        "are resolved at model registration..."
    )
    def test_custom_audit_list_perm_action(self):
        url = reverse("test_audit_log_view")
        plaza_hash = test_audit_registry.hash_model(Plaza)
        shop_hash = test_audit_registry.hash_model(Shop)

        client = self.client
        user = User.objects.create(username="test")

        self.assertTrue(user.has_perm("test_alliance_platform_audit.shop_audit"))
        self.assertFalse(user.has_perm("test_alliance_platform_audit.plaza_audit"))

        # and admin can access shop, so 403 on plaza, 200 on shop and "all"
        client.force_login(user)

        # triggers a creation of one shop & one plaza in db
        client.post(path=reverse("test_audit_create_shop"))

        with self.assertLogs("django.request", "WARNING"):
            response = client.get(f"{url}?model={plaza_hash}")
            self.assertEqual(response.status_code, 403)

        response = client.get(f"{url}?model={shop_hash}")
        self.assertEqual(response.status_code, 200)

        response = client.get(f"{url}?model=all")
        self.assertEqual(response.status_code, 200)

        # additionally, when querying "all", the result from shop should be returned
        # but not the one for plaza
        r = response.json()
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["results"][0]["modelLabel"], "Shop")

    def test_audit_hijack(self):
        customer = User.objects.create(username="hijacked")
        admin = User.objects.create(username="hijacker")

        client = self.client
        client.force_login(admin)
        client.post(reverse("hijack:acquire"), {"user_pk": customer.id}, follow=True)

        url = reverse("test_audit_create_plaza")
        client.post(path=url)
        event = Plaza.AuditEvent.objects.latest("id")
        self.assertEqual(event.pgh_context.metadata, {"url": url, "user": customer.id, "hijacker": admin.id})

    def test_custom_events_from_signals(self):
        client = self.client
        user = User.objects.create(username="test", password="test")
        client.force_login(user)
        self.assertEqual(
            _registration_by_model[User].event_model.objects.count(),
            3,  # CREATE+LOGIN+UPDATE - logging in will also update "last logged in" time
        )

        self.assertEqual(
            _registration_by_model[User].event_model.objects.order_by("pgh_id")[1].pgh_label, "LOGIN"
        )

    def test_inheritance_checks(self):
        class BaseModel(models.Model):
            name = models.CharField(max_length=100)
            ref = models.CharField(max_length=100)

            class Meta:
                app_label = "test_alliance_platform_audit"
                db_table = "test_alliance_platform_audit_base_model"

        class ChildModel(BaseModel):
            child_field = models.CharField(max_length=100)

            class Meta:
                app_label = "test_alliance_platform_audit"
                db_table = "test_alliance_platform_audit_base_model_child"

        with self.assertRaisesRegex(ValueError, r"Fields id, name, ref exist .* not being audited"):
            registry = AuditRegistry()

            class ChildModelEvent1(create_audit_model_base(ChildModel, registry=registry)):
                pass

        with self.assertRaisesRegex(
            ValueError, "Fields id, ref exist only on .* does not include these fields"
        ):
            registry = AuditRegistry()

            class BaseModelEvent(create_audit_model_base(BaseModel, fields=["name"], registry=registry)):
                class Meta:
                    app_label = "test_alliance_platform_audit"

                pass

            class ChildModelEvent2(create_audit_model_base(ChildModel, registry=registry)):
                class Meta:
                    app_label = "test_alliance_platform_audit"

                pass

        # This should work
        class ChildModelEvent3(create_audit_model_base(ChildModel, exclude=["id", "ref"], registry=registry)):
            class Meta:
                app_label = "test_alliance_platform_audit"

            pass

    def test_inheritance(self):
        ProfileFactory.create()
        self.assertEqual(Profile.AuditEvent.objects.count(), 1)
        self.assertEqual(AuthorProfile.AuditEvent.objects.count(), 0)

        author = AuthorProfileFactory.create(homepage="http://example.com/1")
        self.assertEqual(Profile.AuditEvent.objects.count(), 2)
        self.assertEqual(AuthorProfile.AuditEvent.objects.count(), 1)
        author.homepage = "http://example.com/2"
        author.save()
        self.assertEqual(Profile.AuditEvent.objects.count(), 2)
        self.assertEqual(AuthorProfile.AuditEvent.objects.count(), 2)
        author.name = "New Name"
        author.save()
        self.assertEqual(Profile.AuditEvent.objects.count(), 3)
        self.assertEqual(AuthorProfile.AuditEvent.objects.count(), 2)

        with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry):
            request = HttpRequest()
            request.user = UserFactory.create(is_superuser=True)
            request.session = None
            props = get_audit_list_props({"request": request}, object=author, registry=test_audit_registry)
            self.assertEqual(
                props["fieldLabels"],
                {
                    "AuthorProfile": {"homepage": "homepage"},
                    "Profile": {"name": "name", "id": "id"},
                },
            )

    def test_inheritance_deep(self):
        MemberProfileFactory.create()
        self.assertEqual(Profile.AuditEvent.objects.count(), 1)
        self.assertEqual(MemberProfile.AuditEvent.objects.count(), 1)
        super_member = SuperMemberProfileFactory.create()
        self.assertEqual(Profile.AuditEvent.objects.count(), 2)
        self.assertEqual(MemberProfile.AuditEvent.objects.count(), 2)
        self.assertEqual(SuperMemberProfile.AuditEvent.objects.count(), 1)
        super_member.award_points += 10
        super_member.save()
        self.assertEqual(Profile.AuditEvent.objects.count(), 2)
        self.assertEqual(MemberProfile.AuditEvent.objects.count(), 2)
        self.assertEqual(SuperMemberProfile.AuditEvent.objects.count(), 2)

        with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry):
            request = HttpRequest()
            request.user = UserFactory.create(is_superuser=True)
            request.session = None
            props = get_audit_list_props(
                {"request": request}, object=super_member, registry=test_audit_registry
            )
            self.assertEqual(
                props["fieldLabels"],
                {
                    "SuperMemberProfile": {
                        "awardPoints": "award points",
                    },
                    "MemberProfile": {"memberId": "member id"},
                    "Profile": {"id": "id", "name": "name"},
                },
            )

    def test_inheritance_manual_event(self):
        # This event exists on all models; make sure it gets assigned to the one it's called on
        for factory in [ProfileFactory, MemberProfileFactory, SuperMemberProfileFactory]:
            record = factory()
            event = create_audit_event(record, "TRACK")
            self.assertEqual(event.pgh_tracked_model, record.__class__)

        # This event exists on two ancestors; make sure it's tracked against the nearest
        record = SuperMemberProfileFactory.create()
        event = create_audit_event(record, "BOUNCE")
        self.assertIsInstance(event, MemberProfile.AuditEvent)

    def test_manual_event_works_on_m2m(self):
        plaza = AppPlazaFactory(name="Parliament House")
        shop = AppShopFactory(name="Hobgoblin Firecrackers", plaza=plaza)
        m1 = AppPaymentMethodFactory(name="Visa")
        m2 = AppPaymentMethodFactory(name="Master")
        m3 = AppPaymentMethodFactory(name="Potcoin")
        shop.payment_methods_accepted.set([m1, m2, m3])
        # this should work instead of throwing out an error on ManyRelatedManager
        create_audit_event(shop, "REVIEW")
        self.assertCountEqual(
            shop.auditevents.latest("pgh_id").payment_methods_accepted,
            [m1.id, m2.id, m3.id],
        )
        self.assertEqual(shop.auditevents.latest("pgh_id").pgh_label, "REVIEW")

    def test_render_audit_list(self):
        with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry):
            super_member = SuperMemberProfileFactory()
            super_member_alt = SuperMemberProfileFactory()
            create_audit_event(super_member, "REDEEM")
            create_audit_event(super_member_alt, "REFER")
            request = HttpRequest()
            request.user = UserFactory.create(is_superuser=True)
            request.session = None
            props = get_audit_list_props(
                {"request": request}, object=super_member, registry=test_audit_registry
            )
            self.assertEqual(props["labels"], ["CREATE", "REDEEM"])
            props = get_audit_list_props(
                {"request": request}, object=super_member_alt, registry=test_audit_registry
            )
            self.assertEqual(props["labels"], ["CREATE", "REFER"])
            create_audit_event(super_member, "LOGIN")
            props = get_audit_list_props(
                {"request": request}, object=super_member, registry=test_audit_registry
            )
            self.assertEqual(props["labels"], ["CREATE", "LOGIN", "REDEEM"])

            props = get_audit_list_props({"request": request}, model="all", registry=test_audit_registry)
            self.assertEqual(props["labels"], ["CREATE", "LOGIN", "REDEEM", "REFER"])
