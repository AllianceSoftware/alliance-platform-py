from alliance_platform.server_choices import server_choices
from alliance_platform.server_choices.class_handlers.django_filters import FilterSet

from test_alliance_platform_server_choices.models import Shop


# We don't actually need a view for this currently, we just want to register it once for use in test cases
@server_choices()
class TestShopFilterSet(FilterSet):
    class Meta:
        model = Shop
        fields = [
            "plaza",
            "payment_methods_accepted",
        ]


@server_choices(search_fields=["name"], page_size=0)
class TestShopFilterSetWithSearchNoPagination(FilterSet):
    class Meta:
        model = Shop
        fields = [
            "plaza",
            "payment_methods_accepted",
        ]
