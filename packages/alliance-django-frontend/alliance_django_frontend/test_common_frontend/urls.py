from django.urls import path

from common_frontend.test_common_frontend.views import bundler_asset_context_view
from common_frontend.test_common_frontend.views import bundler_ssr_view
from common_frontend.test_common_frontend.views import TestUrlWithPermGlobalView
from common_frontend.test_common_frontend.views import TestUrlWithPermObjectView
from django_site.codegen import DjangoSiteCodeGenConfig
from xenopus_frog_auth.permissions import CheckPermissionsViewSet

app_name = "test_common_frontend"

urlpatterns = [
    path(
        "check-permissions/",
        CheckPermissionsViewSet.as_view(
            permission_manifest_path=DjangoSiteCodeGenConfig.permissions_manifest_path,
        ),
        name="check_permissions",
    ),
    path("bundler-container-ids/", bundler_asset_context_view, name="bundler_container_ids"),
    path("bundler-ssr", bundler_ssr_view, name="bundler_ssr"),
    path(
        "template-tags/url-with-perm-global/",
        TestUrlWithPermGlobalView.as_view(),
        name="url_with_perm_global",
    ),
    path(
        "template-tags/url-with-perm-object/<int:pk>/",
        TestUrlWithPermObjectView.as_view(),
        name="url_with_perm_object",
    ),
    path(
        "template-tags/multiple-args/<int:pk>/<int:area_id>/<slug:code>/",
        TestUrlWithPermObjectView.as_view(),
        name="url_with_multiple_args",
    ),
]
