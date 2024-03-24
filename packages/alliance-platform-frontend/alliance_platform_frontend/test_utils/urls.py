from django.urls import path

from .views import bundler_asset_context_view
from .views import bundler_ssr_view
from .views import TestUrlWithPermGlobalView
from .views import TestUrlWithPermObjectView

app_name = "test_utils"

urlpatterns = [
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
