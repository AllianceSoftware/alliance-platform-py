from django.urls import path

from .views import TestCurrentRequest
from .views import TestLinkRootView
from .views import TestLinkSubView

app_name = "test_alliance_platform_server_choices"

urlpatterns = [
    # current request middleware:
    path("current_request/", TestCurrentRequest.as_view(), name="test_current_request"),
    # {% link %} tag test views:
    path("a/", TestLinkRootView.as_view(), name="test_link_level0"),
    path("a/b/", TestLinkSubView.as_view(), name="test_link_level1"),
    path("a/b/c/", TestLinkSubView.as_view(), name="test_link_level2"),
    # path("with_kwargs/<int:pk>/", TestLinkSelfView.as_view(), name="test_view_user"),
]
