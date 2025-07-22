from alliance_platform.server_choices.views import ServerChoicesView
from django.urls import path

app_name = "test_alliance_platform_server_choices"

urlpatterns = [
    # current request middleware:
    path("test-server-choices/", ServerChoicesView.as_view(), name="test_server_choices"),
]
