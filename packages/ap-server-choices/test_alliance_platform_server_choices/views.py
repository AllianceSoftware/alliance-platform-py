from allianceutils.middleware import CurrentRequestMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import TemplateView

UserModel = get_user_model()


class TestCurrentRequest(TemplateView):
    template_name = "test_server_choices/test_current_request.html"

    def get_context_data(self, **kwargs):
        return {
            "self_request": self.request,
            "current_request": CurrentRequestMiddleware.get_request(),
        }


class TestLinkRootView(TemplateView):
    """Should be publicly accessible"""

    permission_required: None = None
    template_name = "test_server_choices/test_current_request.html"


class TestLinkSubView(PermissionRequiredMixin, TemplateView):
    permission_required = "test_server_choices.link_is_allowed"
    template_name = "test_server_choices/test_current_request.html"
