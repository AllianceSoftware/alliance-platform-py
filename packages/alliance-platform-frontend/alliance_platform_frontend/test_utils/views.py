import json

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.generic import DetailView
from django.views.generic import TemplateView

from ..bundler.context import BundlerAssetContext
from ..templatetags.react import CommonComponentSource
from ..templatetags.react import ComponentProps
from ..templatetags.react import ComponentSSRItem

UserModel = get_user_model()

def bundler_asset_context_view(request: HttpRequest, **kwargs) -> HttpResponse:
    """This view is used to test IDs generated are unique, particularly when generating in different threads"""
    data = json.loads(request.body)
    return JsonResponse(
        {
            "container_ids": [
                BundlerAssetContext.get_current().generate_id() for _ in range(data["containerCount"])
            ]
        }
    )


def bundler_ssr_view(request: HttpRequest, **kwargs) -> HttpResponse:
    """Tests queued SSR items get rendered correctly"""
    data = json.loads(request.body)
    placeholders = []
    # items is a list of strings, e.g. item 1, item 2
    for label in data["items"]:
        item = ComponentSSRItem(
            source=CommonComponentSource("ignored"), props=ComponentProps({}), identifier_prefix=label
        )
        placeholders.append((label, BundlerAssetContext.get_current().queue_ssr(item)))
    if request.accepts("application/json"):
        # this is to trigger check in middleware for non text/html responses
        return JsonResponse({})

    # returns a response like
    #   item 1: <server render here>
    #   item 2: <server render here>
    return HttpResponse("\n".join(f"{label}: {placeholder}" for label, placeholder in placeholders))


class TestUrlWithPermGlobalView(PermissionRequiredMixin, TemplateView):
    permission_required = "test_utils.link_is_allowed"


class TestUrlWithPermObjectView(DetailView):
    permission_required = "test_utils.link_is_allowed"

    model = UserModel

    def has_permission(self):
        return self.request.user.has_perms(self.permission_required, self.get_object())
