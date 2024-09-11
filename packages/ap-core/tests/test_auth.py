from alliance_platform.core.auth import resolve_perm_name
from django.apps import apps
from django.test import TestCase
from test_alliance_platform_core.models import PermTestModelA
from test_alliance_platform_core.models import PermTestModelB

from .test_utils import override_ap_core_settings


class TestAuth(TestCase):
    def test_default_resolve_perm_name(self):
        self.assertEqual(
            resolve_perm_name(PermTestModelA, "list", True),
            "test_alliance_platform_core.permtestmodela_list",
        )

        self.assertEqual(
            resolve_perm_name(PermTestModelB(), "update", False),
            "test_alliance_platform_core.permtestmodelb_update",
        )

        self.assertEqual(
            resolve_perm_name(apps.get_app_config("test_alliance_platform_core"), "management", True),
            "test_alliance_platform_core.management",
        )

    def test_customised_resolve_perm_name(self):
        for setting_value in [resolve_perm_name_for_testing, "tests.test_auth.resolve_perm_name_for_testing"]:
            with self.subTest(setting_value=setting_value):
                with override_ap_core_settings(RESOLVE_PERM_NAME=setting_value):
                    self.assertEqual(
                        resolve_perm_name(PermTestModelA, "list", True),
                        "test_alliance_platform_core|permtestmodela|list|True",
                    )

                    self.assertEqual(
                        resolve_perm_name(PermTestModelB, "update", False),
                        "test_alliance_platform_core|permtestmodelb|update|False",
                    )

                    self.assertEqual(
                        resolve_perm_name(
                            apps.get_app_config("test_alliance_platform_core"), "management", True
                        ),
                        "test_alliance_platform_core|management|True",
                    )


def resolve_perm_name_for_testing(app_config, model, action, is_global):
    if model:
        return f"{app_config.label}|{model._meta.model_name}|{action}|{is_global}"
    return f"{app_config.label}|{action}|{is_global}"
