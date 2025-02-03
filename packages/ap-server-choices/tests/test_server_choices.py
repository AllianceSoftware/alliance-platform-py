import json

from alliance_platform.server_choices import server_choices
from alliance_platform.server_choices.form import ServerChoicesSelectWidget
from alliance_platform.server_choices.register import ServerChoicesRegistry
from alliance_platform.server_choices.views import ServerChoicesView
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ObjectDoesNotExist
from django.forms import ModelForm
from django.forms import ModelMultipleChoiceField
from django.forms.widgets import RadioSelect
from django.http import HttpRequest
from django.http import QueryDict
from django.test import TestCase
from django_filters import FilterSet
from django_filters import ModelMultipleChoiceFilter
from django_filters import filters
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
from rest_framework.test import force_authenticate
from test_alliance_platform_server_choices.factory import AppPaymentMethodFactory
from test_alliance_platform_server_choices.factory import AppPlazaFactory
from test_alliance_platform_server_choices.factory import AppShopFactory
from test_alliance_platform_server_choices.models import PaymentMethod
from test_alliance_platform_server_choices.models import Plaza
from test_alliance_platform_server_choices.models import Shop
from test_alliance_platform_server_choices.models import ShopCategory
from xenopus_frog_app.base import XenopusFrogAppModelSerializer
from xenopus_frog_app.tests.user_type_defs import AppAdminProfileFactory


def get_choices(registration, request):
    if isinstance(registration.field.choices, dict):
        items = registration.field.choices.items()
    else:
        items = registration.field.choices
    return [[f"PK-{key}" if key != "" else "", label.upper()] for key, label in items]


def get_record(registration, pk, request):
    for key, value in registration.get_choices(request):
        if key == f"PK-{pk}":
            return (key, value)
    raise ObjectDoesNotExist()


def get_records(registration, pks, request):
    records = []
    for key, value in registration.get_choices(request):
        if key != "" and int(key.split("PK-")[1]) in [int(x) for x in pks]:
            records.append([key, value])
    return records


def serialize(registration, item_or_items, request):
    # Just returns choices as tuples rather than dict with key/label keys
    return item_or_items


def filter_choices(registration, choices, request):
    query = request.query_params.get("query")
    matched_choices = []
    query = [keyword.lower() for keyword in filter(bool, query.split(" "))]
    for key, label in choices:
        if all([keyword in label.lower() for keyword in query]):
            matched_choices.append([key, label])
    return matched_choices


class TestSerializerServerChoices(TestCase):
    def test_handles_invalid_fields(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "do not exist on"):

            @server_choices(["plaza"], registry=ServerChoicesRegistry("test"))
            class TestShopSerializer1(XenopusFrogAppModelSerializer):
                class Meta:
                    model = Shop
                    fields = ["name"]

        with self.assertWarns(UserWarning, msg="Field plaza already registered"):
            registry = ServerChoicesRegistry("test")

            @server_choices(["plaza"], registry=registry)
            @server_choices(["plaza"], registry=registry)
            class TestShopSerializer2(XenopusFrogAppModelSerializer):
                class Meta:
                    model = Shop
                    fields = ["name", "plaza"]

    def test_identifies_fields(self):
        registry = ServerChoicesRegistry("test")

        # No fields specified; should extract all related fields
        @server_choices(registry=registry)
        class TestShopSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = Shop
                fields = [
                    "id",
                    "name",
                    "plaza",
                    "category",
                    "payment_methods_accepted",
                ]

        self.assertCountEqual(
            list(registry.server_choices_registry.values())[0].fields.keys(),
            [
                "plaza",
                "payment_methods_accepted",
            ],
        )

    def test_many_related_field(self):
        for _ in range(20):
            AppPaymentMethodFactory()

        payment_methods = list(PaymentMethod.objects.all())

        registry = ServerChoicesRegistry("test")

        @server_choices(search_fields=["name"], registry=registry)
        class TestShopSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = Shop
                fields = [
                    "payment_methods_accepted",
                ]

        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopSerializer)
        payment_methods_field = list(registry.server_choices_registry.values())[0].fields[
            "payment_methods_accepted"
        ]
        self.assertEqual(payment_methods_field.perm, "test_alliance_platform_server_choices.shop_create")
        self.assertEqual(list(payment_methods_field.get_choices(request)), payment_methods)
        payment_method = payment_methods[0]
        self.assertEqual(payment_methods_field.get_record(payment_method.pk, request), payment_method)
        types = payment_methods[:3]
        self.assertEqual(list(payment_methods_field.get_records([t.pk for t in types], request)), types)
        self.assertEqual(
            payment_methods_field.serialize(types, request),
            [{"key": record.pk, "label": str(record)} for record in types],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=visa")
        self.assertEqual(
            list(payment_methods_field.filter_choices(payment_methods_field.get_choices(request), request)),
            list(PaymentMethod.objects.filter(name__icontains="visa")),
        )

    def test_reverse_relation(self):
        method = AppPaymentMethodFactory()
        plaza1 = AppPlazaFactory(name="Blackburn Mall")
        plaza2 = AppPlazaFactory(name="Chadstone")
        shop1 = AppShopFactory(name="Shelley's Seafood", plaza=plaza1)
        shop1.payment_methods_accepted.set([method])
        shop2 = AppShopFactory(name="Wiley Footwear", plaza=plaza2)
        shop2.payment_methods_accepted.set([method])
        shop3 = AppShopFactory(name="Seafood Bonanza", plaza=plaza2)
        shop3.payment_methods_accepted.set([method])

        registry = ServerChoicesRegistry("test")

        @server_choices(search_fields=["name", "plaza__name"], registry=registry)
        class TestPaymentMethodSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = PaymentMethod
                fields = [
                    "shops",
                ]

        request = HttpRequest()
        self.assertEqual(
            list(registry.server_choices_registry.values())[0].source,
            TestPaymentMethodSerializer,
        )
        shops_field = list(registry.server_choices_registry.values())[0].fields["shops"]
        self.assertEqual(shops_field.perm, "test_alliance_platform_server_choices.paymentmethod_create")
        shops = [shop1, shop2, shop3]
        self.assertEqual(list(shops_field.get_choices(request)), shops)
        self.assertEqual(shops_field.get_record(shop1.pk, request), shop1)
        sub_shops = shops[:2]
        self.assertEqual(list(shops_field.get_records([t.pk for t in sub_shops], request)), sub_shops)
        self.assertEqual(
            shops_field.serialize(sub_shops, request),
            [{"key": record.pk, "label": str(record)} for record in sub_shops],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=blackburn")
        self.assertEqual(
            list(shops_field.filter_choices(shops_field.get_choices(request), request)),
            [shop1],
        )
        request.query_params = QueryDict("keywords=chadstone")
        self.assertEqual(
            list(shops_field.filter_choices(shops_field.get_choices(request), request)),
            [shop2, shop3],
        )
        # multiple keywords; this should match plaza title and shop name
        request.query_params = QueryDict("keywords=chadstone wiley")
        self.assertEqual(
            list(shops_field.filter_choices(shops_field.get_choices(request), request)),
            [shop2],
        )

    def test_regular_choices(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(["category"], registry=registry)
        class TestShopSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopSerializer)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        self.assertEqual(category_field.perm, "test_alliance_platform_server_choices.shop_create")
        self.assertEqual(category_field.get_choices(request), ShopCategory.choices)
        (pk, label) = ShopCategory.choices[0]
        self.assertEqual(category_field.get_record(pk, request), (pk, label))
        choices = ShopCategory.choices
        self.assertEqual(category_field.get_records([t[0] for t in choices], request), choices)
        self.assertEqual(
            category_field.serialize(choices, request),
            [{"key": key, "label": label} for (key, label) in choices],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=grocery")
        self.assertEqual(
            category_field.filter_choices(category_field.get_choices(request), request),
            [ShopCategory.choices[0]],
        )

    def test_get_choices_supports_queryset(self):
        registry = ServerChoicesRegistry("test")

        department_store = AppShopFactory(category=ShopCategory.DEPARTMENT)
        # Other.
        AppShopFactory()

        @server_choices(
            ["category"], registry=registry, get_choices=Shop.objects.filter(category=ShopCategory.DEPARTMENT)
        )
        class TestShopSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopSerializer)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        request = HttpRequest()
        self.assertCountEqual(
            [department_store],
            category_field.get_choices(request),
        )

    def test_customise(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(
            ["category"],
            get_choices=get_choices,
            get_record=get_record,
            get_records=get_records,
            serialize=serialize,
            filter_choices=filter_choices,
            registry=registry,
        )
        class TestShopSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        upper_choices = [[f"PK-{key}", label.upper()] for key, label in ShopCategory.choices]
        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopSerializer)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        self.assertEqual(
            category_field.get_choices(request),
            upper_choices,
        )
        self.assertEqual(
            category_field.get_record(ShopCategory.GROCERY.value, request),
            (f"PK-{ShopCategory.GROCERY.value}", ShopCategory.GROCERY.label.upper()),
        )
        self.assertEqual(
            category_field.get_records([t[0] for t in ShopCategory.choices], request), upper_choices
        )
        self.assertEqual(
            category_field.serialize(category_field.get_choices(request), request), upper_choices
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("query=grocery")
        self.assertEqual(
            category_field.filter_choices(category_field.get_choices(request), request),
            [upper_choices[0]],
        )

    def test_server_choices_view(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(
            ["category"],
            pagination_class=None,
            registry=registry,
        )
        class TestShopSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        user = AppAdminProfileFactory(is_superuser=True)
        factory = APIRequestFactory()
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category"
        )
        force_authenticate(request, user=user)
        view = ServerChoicesView.as_view(registry=registry)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            category_field.serialize(category_field.get_choices({}), request),
        )

        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category&pk={ShopCategory.GROCERY.value}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            {
                "label": ShopCategory.GROCERY.label,
                "key": ShopCategory.GROCERY.value,
            },
        )

        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category&pks={ShopCategory.GROCERY.value}&pks={ShopCategory.DEPARTMENT.value}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            [
                {
                    "label": ShopCategory.GROCERY.label,
                    "key": ShopCategory.GROCERY.value,
                },
                {
                    "label": ShopCategory.DEPARTMENT.label,
                    "key": ShopCategory.DEPARTMENT.value,
                },
            ],
        )

    def test_server_choices_view_pagination(self):
        registry = ServerChoicesRegistry("test")

        for i in range(30):
            AppPlazaFactory()

        @server_choices(
            ["plaza"],
            registry=registry,
        )
        class TestShopSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = Shop
                fields = [
                    "plaza",
                ]

        plaza_field = list(registry.server_choices_registry.values())[0].fields["plaza"]
        user = AppAdminProfileFactory(is_superuser=True)
        factory = APIRequestFactory()
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza"
        )
        force_authenticate(request, user=user)
        view = ServerChoicesView.as_view(registry=registry)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(data["count"], 30)
        self.assertEqual(
            data["results"], plaza_field.serialize(Plaza.objects.all()[: api_settings.PAGE_SIZE], request)
        )

    def test_get_label(self):
        registry = ServerChoicesRegistry("test")

        for i in range(30):
            AppPlazaFactory()

        plaza1, plaza2 = Plaza.objects.all()[:2]

        @server_choices(
            ["plaza"], registry=registry, get_label=lambda registry, item: f"Plaza: {str(item)} {item.pk}"
        )
        class TestShopSerializer(XenopusFrogAppModelSerializer):
            class Meta:
                model = Shop
                fields = [
                    "plaza",
                ]

        user = AppAdminProfileFactory(is_superuser=True)
        factory = APIRequestFactory()
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza"
        )
        force_authenticate(request, user=user)
        view = ServerChoicesView.as_view(registry=registry)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(data["count"], 30)
        self.assertEqual(
            data["results"],
            [
                {"key": p.pk, "label": f"Plaza: {str(p)} {p.pk}"}
                for p in Plaza.objects.all()[: api_settings.PAGE_SIZE]
            ],
        )

        # Fetch single record
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza&pk={plaza1.pk}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(data, {"key": plaza1.pk, "label": f"Plaza: {str(plaza1)} {plaza1.pk}"})

        # Fetch single record
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza&pks={plaza1.pk}&pks={plaza2.pk}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(
            data,
            [
                {"key": plaza1.pk, "label": f"Plaza: {str(plaza1)} {plaza1.pk}"},
                {"key": plaza2.pk, "label": f"Plaza: {str(plaza2)} {plaza2.pk}"},
            ],
        )


class TestFormServerChoices(TestCase):
    def test_handles_invalid_fields(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "do not exist on"):

            @server_choices(["plaza"], registry=ServerChoicesRegistry("test"))
            class ShopForm1(ModelForm):
                class Meta:
                    model = Shop
                    fields = ["name"]

        with self.assertWarns(UserWarning, msg="Field plaza already registered"):
            registry = ServerChoicesRegistry("test")

            @server_choices(["plaza"], registry=registry)
            @server_choices(["plaza"], registry=registry)
            class ShopForm2(ModelForm):
                class Meta:
                    model = Shop
                    fields = ["name", "plaza"]

    def test_identifies_fields(self):
        registry = ServerChoicesRegistry("test")

        # No fields specified; should extract all related fields
        @server_choices(registry=registry)
        class TestShopForm(ModelForm):
            class Meta:
                model = Shop
                fields = [
                    "id",
                    "name",
                    "plaza",
                    "category",
                    "payment_methods_accepted",
                ]

        self.assertCountEqual(
            list(registry.server_choices_registry.values())[0].fields.keys(),
            [
                "plaza",
                "payment_methods_accepted",
            ],
        )

    def test_many_related_field(self):
        for _ in range(20):
            AppPaymentMethodFactory()

        payment_methods = list(PaymentMethod.objects.all())

        registry = ServerChoicesRegistry("test")

        @server_choices(search_fields=["name"], registry=registry)
        class TestShopForm(ModelForm):
            class Meta:
                model = Shop
                fields = [
                    "payment_methods_accepted",
                ]

        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopForm)
        payment_methods_field = list(registry.server_choices_registry.values())[0].fields[
            "payment_methods_accepted"
        ]
        self.assertEqual(payment_methods_field.perm, "test_alliance_platform_server_choices.shop_create")
        self.assertEqual(list(payment_methods_field.get_choices(request)), payment_methods)
        payment_method = payment_methods[0]
        self.assertEqual(payment_methods_field.get_record(payment_method.pk, request), payment_method)
        types = payment_methods[:3]
        self.assertEqual(list(payment_methods_field.get_records([t.pk for t in types], request)), types)
        self.assertEqual(
            payment_methods_field.serialize(types, request),
            [{"key": str(record.pk), "label": str(record)} for record in types],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=visa")
        self.assertEqual(
            list(payment_methods_field.filter_choices(payment_methods_field.get_choices(request), request)),
            list(PaymentMethod.objects.filter(name__icontains="visa")),
        )

    def test_reverse_relation(self):
        method = AppPaymentMethodFactory()
        plaza1 = AppPlazaFactory(name="Blackburn Mall")
        plaza2 = AppPlazaFactory(name="Chadstone")
        shop1 = AppShopFactory(name="Shelley's Seafood", plaza=plaza1)
        shop1.payment_methods_accepted.set([method])
        shop2 = AppShopFactory(name="Wiley Footwear", plaza=plaza2)
        shop2.payment_methods_accepted.set([method])
        shop3 = AppShopFactory(name="Seafood Bonanza", plaza=plaza2)
        shop3.payment_methods_accepted.set([method])

        registry = ServerChoicesRegistry("test")

        @server_choices(search_fields=["name", "plaza__name"], registry=registry)
        class TestPaymentMethodForm(ModelForm):
            shops = ModelMultipleChoiceField(queryset=Shop.objects.all())

            class Meta:
                model = PaymentMethod
                fields = [
                    "shops",
                ]

        request = HttpRequest()
        self.assertEqual(
            list(registry.server_choices_registry.values())[0].source,
            TestPaymentMethodForm,
        )
        shops_field = list(registry.server_choices_registry.values())[0].fields["shops"]
        self.assertEqual(shops_field.perm, "test_alliance_platform_server_choices.paymentmethod_create")
        shops = [shop1, shop2, shop3]
        self.assertEqual(list(shops_field.get_choices(request)), shops)
        self.assertEqual(shops_field.get_record(shop1.pk, request), shop1)
        sub_shops = shops[:2]
        self.assertEqual(list(shops_field.get_records([t.pk for t in sub_shops], request)), sub_shops)
        self.assertEqual(
            shops_field.serialize(sub_shops, request),
            [{"key": str(record.pk), "label": str(record)} for record in sub_shops],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=blackburn")

        def sorter(shops):
            return sorted(list(shops), key=lambda shop: shop.pk)

        self.assertEqual(
            sorter(shops_field.filter_choices(shops_field.get_choices(request), request)),
            [shop1],
        )
        request.query_params = QueryDict("keywords=chadstone")
        self.assertEqual(
            sorter(shops_field.filter_choices(shops_field.get_choices(request), request)),
            sorter([shop2, shop3]),
        )
        # multiple keywords; this should match plaza title and shop name
        request.query_params = QueryDict("keywords=chadstone wiley")
        self.assertEqual(
            sorter(shops_field.filter_choices(shops_field.get_choices(request), request)),
            [shop2],
        )

    def test_regular_choices(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(["category"], registry=registry)
        class TestShopForm(ModelForm):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopForm)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        self.assertEqual(category_field.perm, "test_alliance_platform_server_choices.shop_create")
        self.assertEqual(category_field.get_choices(request), ShopCategory.choices)
        (pk, label) = ShopCategory.choices[0]
        self.assertEqual(category_field.get_record(pk, request), (str(pk), label))
        # We always deal with string keys for Forms to avoid type mismatches
        choices = [(str(key), value) for key, value in ShopCategory.choices]
        self.assertEqual(category_field.get_records([t[0] for t in choices], request), choices)
        self.assertEqual(
            category_field.serialize(choices, request),
            [{"key": key, "label": label} for (key, label) in choices],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=grocery")
        self.assertEqual(
            category_field.filter_choices(category_field.get_choices(request), request),
            [ShopCategory.choices[0]],
        )

    def test_get_choices_supports_queryset(self):
        registry = ServerChoicesRegistry("test")

        department_store = AppShopFactory(category=ShopCategory.DEPARTMENT)
        # Other.
        AppShopFactory()

        @server_choices(
            ["category"], registry=registry, get_choices=Shop.objects.filter(category=ShopCategory.DEPARTMENT)
        )
        class TestShopForm(ModelForm):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopForm)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        request = HttpRequest()

        # make sure the get_choices query was not executed up until this point
        self.assertIsNone(category_field.get_choices(request)._result_cache)

        self.assertEqual(
            list(category_field.get_choices(request)),
            [department_store],
        )

    def test_customise(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(
            ["category"],
            get_choices=get_choices,
            get_record=get_record,
            get_records=get_records,
            serialize=serialize,
            filter_choices=filter_choices,
            registry=registry,
        )
        class TestShopForm(ModelForm):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        upper_choices = [[f"PK-{key}", label.upper()] for key, label in ShopCategory.choices]
        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopForm)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        self.assertEqual(
            category_field.get_choices(request),
            upper_choices,
        )
        self.assertEqual(
            category_field.get_record(ShopCategory.GROCERY.value, request),
            (f"PK-{ShopCategory.GROCERY.value}", ShopCategory.GROCERY.label.upper()),
        )
        self.assertEqual(
            category_field.get_records([t[0] for t in ShopCategory.choices], request), upper_choices
        )
        self.assertEqual(
            category_field.serialize(category_field.get_choices(request), request), upper_choices
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("query=grocery")
        self.assertEqual(
            category_field.filter_choices(category_field.get_choices(request), request),
            [upper_choices[0]],
        )

    def test_server_choices_view(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(
            ["category"],
            pagination_class=None,
            registry=registry,
        )
        class TestShopForm(ModelForm):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        user = AppAdminProfileFactory(is_superuser=True)
        factory = APIRequestFactory()
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category"
        )
        force_authenticate(request, user=user)
        view = ServerChoicesView.as_view(registry=registry)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            category_field.serialize(category_field.get_choices({}), request),
        )

        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category&pk={ShopCategory.GROCERY.value}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            {
                "label": ShopCategory.GROCERY.label,
                "key": str(ShopCategory.GROCERY.value),
            },
        )

        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category&pks={ShopCategory.GROCERY.value}&pks={ShopCategory.DEPARTMENT.value}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            [
                {
                    "label": ShopCategory.GROCERY.label,
                    "key": str(ShopCategory.GROCERY.value),
                },
                {
                    "label": ShopCategory.DEPARTMENT.label,
                    "key": str(ShopCategory.DEPARTMENT.value),
                },
            ],
        )

    def test_server_choices_view_pagination(self):
        for i in range(30):
            AppPlazaFactory()

        kwargs = {}
        for empty_label in ["(infer)", None, "Please Select"]:
            with self.subTest(f"empty_label={empty_label}"):
                registry = ServerChoicesRegistry("test")

                if empty_label != "(infer)":
                    kwargs["empty_label"] = empty_label

                @server_choices(["plaza"], registry=registry, **kwargs)
                class TestShopForm(ModelForm):
                    class Meta:
                        model = Shop
                        fields = [
                            "plaza",
                        ]

                plaza_field = list(registry.server_choices_registry.values())[0].fields["plaza"]
                user = AppAdminProfileFactory(is_superuser=True)
                factory = APIRequestFactory()
                request = factory.get(
                    f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza"
                )
                force_authenticate(request, user=user)
                view = ServerChoicesView.as_view(registry=registry)
                response = view(request).render()
                self.assertEqual(response.status_code, 200)
                data = json.loads(response.content.decode())
                self.assertEqual(data["count"], 30)
                records = plaza_field.serialize(Plaza.objects.all()[: api_settings.PAGE_SIZE], request)
                self.assertEqual(
                    data["results"],
                    (
                        [
                            {"key": "", "label": "---------" if empty_label == "(infer)" else empty_label},
                            *records,
                        ]
                        if empty_label is not None
                        else records
                    ),
                )

    def test_get_label(self):
        registry = ServerChoicesRegistry("test")

        for i in range(30):
            AppPlazaFactory()

        plaza1, plaza2 = Plaza.objects.all()[:2]

        @server_choices(
            ["plaza"],
            registry=registry,
            get_label=lambda registry, item: f"Plaza: {str(item)} {item.pk}",
            empty_label=None,
        )
        class TestShopForm(ModelForm):
            class Meta:
                model = Shop
                fields = [
                    "plaza",
                ]

        user = AppAdminProfileFactory(is_superuser=True)
        factory = APIRequestFactory()
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza"
        )
        force_authenticate(request, user=user)
        view = ServerChoicesView.as_view(registry=registry)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(data["count"], 30)
        self.assertEqual(
            data["results"],
            [
                {"key": str(p.pk), "label": f"Plaza: {str(p)} {p.pk}"}
                for p in Plaza.objects.all()[: api_settings.PAGE_SIZE]
            ],
        )

        # Fetch single record
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza&pk={plaza1.pk}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(data, {"key": str(plaza1.pk), "label": f"Plaza: {str(plaza1)} {plaza1.pk}"})

        # Fetch single record
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza&pks={plaza1.pk}&pks={plaza2.pk}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(
            data,
            [
                {"key": str(plaza1.pk), "label": f"Plaza: {str(plaza1)} {plaza1.pk}"},
                {"key": str(plaza2.pk), "label": f"Plaza: {str(plaza2)} {plaza2.pk}"},
            ],
        )

    def test_field_widget(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(
            registry=registry,
        )
        class TestShopForm(ModelForm):
            class Meta:
                model = Shop
                fields = [
                    "plaza",
                ]

        form = TestShopForm()
        self.assertIsInstance(form.fields["plaza"].widget, ServerChoicesSelectWidget)

    def test_field_widget_validation(self):
        with self.assertRaisesRegex(ValueError, "widget must be either Select or SelectMultiple"):
            registry = ServerChoicesRegistry("test")

            @server_choices(fields=["plaza"], registry=registry)
            class TestShopForm(ModelForm):
                plaza = ModelMultipleChoiceField(queryset=Shop.objects.all(), widget=RadioSelect)

                class Meta:
                    model = Shop
                    fields = [
                        "plaza",
                    ]


class TestFilterSetServerChoices(TestCase):
    def test_handles_invalid_fields(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "do not exist on"):

            @server_choices(["plaza"], registry=ServerChoicesRegistry("test"))
            class ShopFilterSet1(FilterSet):
                class Meta:
                    model = Shop
                    fields = ["name"]

        with self.assertWarns(UserWarning, msg="Field plaza already registered"):
            registry = ServerChoicesRegistry("test")

            @server_choices(["plaza"], registry=registry)
            @server_choices(["plaza"], registry=registry)
            class ShopFilterSet2(FilterSet):
                class Meta:
                    model = Shop
                    fields = ["name", "plaza"]

    def test_identifies_fields(self):
        registry = ServerChoicesRegistry("test")

        # No fields specified; should extract all related fields
        @server_choices(registry=registry)
        class TestShopFilterSet(FilterSet):
            class Meta:
                model = Shop
                fields = [
                    "id",
                    "name",
                    "plaza",
                    "category",
                    "payment_methods_accepted",
                ]

        self.assertCountEqual(
            list(registry.server_choices_registry.values())[0].fields.keys(),
            [
                "plaza",
                "payment_methods_accepted",
            ],
        )

    def test_many_related_field(self):
        for _ in range(20):
            AppPaymentMethodFactory()

        payment_methods = list(PaymentMethod.objects.all())

        registry = ServerChoicesRegistry("test")

        @server_choices(search_fields=["name"], registry=registry)
        class TestShopFilterSet(FilterSet):
            class Meta:
                model = Shop
                fields = [
                    "payment_methods_accepted",
                ]

        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopFilterSet)
        payment_methods_field = list(registry.server_choices_registry.values())[0].fields[
            "payment_methods_accepted"
        ]
        self.assertEqual(payment_methods_field.perm, "test_alliance_platform_server_choices.shop_create")
        self.assertEqual(list(payment_methods_field.get_choices(request)), payment_methods)
        payment_method = payment_methods[0]
        self.assertEqual(payment_methods_field.get_record(payment_method.pk, request), payment_method)
        types = payment_methods[:3]
        self.assertEqual(list(payment_methods_field.get_records([t.pk for t in types], request)), types)
        self.assertEqual(
            payment_methods_field.serialize(types, request),
            [{"key": str(record.pk), "label": str(record)} for record in types],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=visa")
        self.assertEqual(
            list(payment_methods_field.filter_choices(payment_methods_field.get_choices(request), request)),
            list(PaymentMethod.objects.filter(name__icontains="visa")),
        )

    def test_reverse_relation(self):
        method = AppPaymentMethodFactory()
        plaza1 = AppPlazaFactory(name="Blackburn Mall")
        plaza2 = AppPlazaFactory(name="Chadstone")
        shop1 = AppShopFactory(name="Shelley's Seafood", plaza=plaza1)
        shop1.payment_methods_accepted.set([method])
        shop2 = AppShopFactory(name="Wiley Footwear", plaza=plaza2)
        shop2.payment_methods_accepted.set([method])
        shop3 = AppShopFactory(name="Seafood Bonanza", plaza=plaza2)
        shop3.payment_methods_accepted.set([method])

        registry = ServerChoicesRegistry("test")

        @server_choices(search_fields=["name", "plaza__name"], registry=registry)
        class TestPaymentMethodFilterSet(FilterSet):
            shops = ModelMultipleChoiceFilter(queryset=Shop.objects.order_by("name"))

            class Meta:
                model = PaymentMethod
                fields = [
                    "shops",
                ]

        request = HttpRequest()
        self.assertEqual(
            list(registry.server_choices_registry.values())[0].source,
            TestPaymentMethodFilterSet,
        )
        shops_field = list(registry.server_choices_registry.values())[0].fields["shops"]
        self.assertEqual(shops_field.perm, "test_alliance_platform_server_choices.paymentmethod_create")
        shops = [shop3, shop1, shop2]  # order is alphabetised by name
        self.assertEqual(list(shops_field.get_choices(request)), shops)
        self.assertEqual(shops_field.get_record(shop1.pk, request), shop1)
        sub_shops = shops[:2]
        self.assertEqual(list(shops_field.get_records([t.pk for t in sub_shops], request)), sub_shops)
        self.assertEqual(
            shops_field.serialize(sub_shops, request),
            [{"key": str(record.pk), "label": str(record)} for record in sub_shops],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=blackburn")
        self.assertEqual(
            list(shops_field.filter_choices(shops_field.get_choices(request), request)),
            [shop1],
        )
        request.query_params = QueryDict("keywords=chadstone")
        self.assertEqual(
            list(shops_field.filter_choices(shops_field.get_choices(request), request)),
            [shop3, shop2],
        )
        # multiple keywords; this should match plaza title and shop name
        request.query_params = QueryDict("keywords=chadstone wiley")
        self.assertEqual(
            list(shops_field.filter_choices(shops_field.get_choices(request), request)),
            [shop2],
        )

    def test_regular_choices(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(["category"], registry=registry)
        class TestShopFilterSet(FilterSet):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopFilterSet)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        self.assertEqual(category_field.perm, "test_alliance_platform_server_choices.shop_create")
        self.assertEqual(
            list(category_field.get_choices(request)), [("", "---------"), *ShopCategory.choices]
        )
        (pk, label) = ShopCategory.choices[0]
        self.assertEqual(category_field.get_record(pk, request), (str(pk), label))
        # We always deal with string keys for FilterSets void type mismatches
        choices = [(str(key), value) for key, value in ShopCategory.choices]
        self.assertEqual(category_field.get_records([t[0] for t in choices], request), choices)
        self.assertEqual(
            category_field.serialize(choices, request),
            [{"key": key, "label": label} for (key, label) in choices],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("keywords=grocery")
        self.assertEqual(
            category_field.filter_choices(category_field.get_choices(request), request),
            [ShopCategory.choices[0]],
        )

    def test_get_choices_supports_queryset(self):
        registry = ServerChoicesRegistry("test")

        department_store = AppShopFactory(category=ShopCategory.DEPARTMENT)
        # Other.
        AppShopFactory()

        @server_choices(
            ["category"], registry=registry, get_choices=Shop.objects.filter(category=ShopCategory.DEPARTMENT)
        )
        class TestShopFilterSet(FilterSet):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopFilterSet)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        request = HttpRequest()
        self.assertCountEqual(
            [department_store],
            category_field.get_choices(request),
        )

    def test_customise(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(
            ["category"],
            get_choices=get_choices,
            get_record=get_record,
            get_records=get_records,
            serialize=serialize,
            filter_choices=filter_choices,
            registry=registry,
        )
        class TestShopFilterSet(FilterSet):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        upper_choices = [[f"PK-{key}", label.upper()] for key, label in ShopCategory.choices]
        request = HttpRequest()
        self.assertEqual(list(registry.server_choices_registry.values())[0].source, TestShopFilterSet)
        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        self.assertEqual(
            category_field.get_choices(request),
            [["", "---------"], *upper_choices],
        )
        self.assertEqual(
            category_field.get_record(ShopCategory.GROCERY.value, request),
            (f"PK-{ShopCategory.GROCERY.value}", ShopCategory.GROCERY.label.upper()),
        )
        self.assertEqual(
            category_field.get_records([t[0] for t in ShopCategory.choices if t[0] != ""], request),
            upper_choices,
        )
        self.assertEqual(
            category_field.serialize(category_field.get_choices(request), request),
            [["", "---------"], *upper_choices],
        )
        # query_params is only on DRF request but can't easily create that... even APIRequestFactory from
        # DRF doesn't return it (it gets promoted once it goes through the view layer). Just fake it here -
        # all we care about is query_params
        request.query_params = QueryDict("query=grocery")
        self.assertEqual(
            category_field.filter_choices(category_field.get_choices(request), request),
            [upper_choices[0]],
        )

    def test_server_choices_view(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(
            ["category"],
            pagination_class=None,
            registry=registry,
        )
        class TestShopFilterSet(FilterSet):
            class Meta:
                model = Shop
                fields = [
                    "category",
                ]

        category_field = list(registry.server_choices_registry.values())[0].fields["category"]
        user = AppAdminProfileFactory(is_superuser=True)
        factory = APIRequestFactory()
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category"
        )
        force_authenticate(request, user=user)
        view = ServerChoicesView.as_view(registry=registry)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            [
                {"key": "", "label": "---------"},
                *category_field.serialize(category_field.get_choices({}), request),
            ],
        )

        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category&pk={ShopCategory.GROCERY.value}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            {
                "label": ShopCategory.GROCERY.label,
                "key": str(ShopCategory.GROCERY.value),
            },
        )

        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=category&pks={ShopCategory.GROCERY.value}&pks={ShopCategory.DEPARTMENT.value}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode()),
            [
                {
                    "label": ShopCategory.GROCERY.label,
                    "key": str(ShopCategory.GROCERY.value),
                },
                {
                    "label": ShopCategory.DEPARTMENT.label,
                    "key": str(ShopCategory.DEPARTMENT.value),
                },
            ],
        )

    def test_server_choices_view_pagination(self):
        for i in range(30):
            AppPlazaFactory()

        kwargs = {}
        for empty_label in ["(infer)", None, "Please Select"]:
            with self.subTest(f"empty_label={empty_label}"):
                registry = ServerChoicesRegistry("test")

                if empty_label != "(infer)":
                    kwargs["empty_label"] = empty_label

                @server_choices(["plaza"], registry=registry, **kwargs)
                class TestShopFilterSet(FilterSet):
                    class Meta:
                        model = Shop
                        fields = [
                            "plaza",
                        ]

                plaza_field = list(registry.server_choices_registry.values())[0].fields["plaza"]
                user = AppAdminProfileFactory(is_superuser=True)
                factory = APIRequestFactory()
                request = factory.get(
                    f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza"
                )
                force_authenticate(request, user=user)
                view = ServerChoicesView.as_view(registry=registry)
                response = view(request).render()
                self.assertEqual(response.status_code, 200)
                data = json.loads(response.content.decode())
                self.assertEqual(data["count"], 30)
                records = plaza_field.serialize(Plaza.objects.all()[: api_settings.PAGE_SIZE], request)
                self.assertEqual(
                    data["results"],
                    (
                        [
                            {"key": "", "label": "---------" if empty_label == "(infer)" else empty_label},
                            *records,
                        ]
                        if empty_label is not None
                        else records
                    ),
                )

    def test_get_label(self):
        registry = ServerChoicesRegistry("test")

        for i in range(30):
            AppPlazaFactory()

        plaza1, plaza2 = Plaza.objects.all()[:2]

        @server_choices(
            ["plaza"],
            registry=registry,
            get_label=lambda registry, item: f"Plaza: {str(item)} {item.pk}",
            empty_label=None,
        )
        class TestShopFilterSet(FilterSet):
            class Meta:
                model = Shop
                fields = [
                    "plaza",
                ]

        user = AppAdminProfileFactory(is_superuser=True)
        factory = APIRequestFactory()
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza"
        )
        force_authenticate(request, user=user)
        view = ServerChoicesView.as_view(registry=registry)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(data["count"], 30)
        self.assertEqual(
            data["results"],
            [
                {"key": str(p.pk), "label": f"Plaza: {str(p)} {p.pk}"}
                for p in Plaza.objects.all()[: api_settings.PAGE_SIZE]
            ],
        )

        # Fetch single record
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza&pk={plaza1.pk}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(data, {"key": str(plaza1.pk), "label": f"Plaza: {str(plaza1)} {plaza1.pk}"})

        # Fetch single record
        request = factory.get(
            f"/?class_name={list(registry.server_choices_registry.keys())[0]}&field_name=plaza&pks={plaza1.pk}&pks={plaza2.pk}"
        )
        force_authenticate(request, user=user)
        response = view(request).render()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(
            data,
            [
                {"key": str(plaza1.pk), "label": f"Plaza: {str(plaza1)} {plaza1.pk}"},
                {"key": str(plaza2.pk), "label": f"Plaza: {str(plaza2)} {plaza2.pk}"},
            ],
        )

    def test_server_choices_works_with_modelchoicefilter_callable_querysets(self):
        registry = ServerChoicesRegistry("test")
        werribee_plaza = Plaza.objects.create(name="Werribee Plaza")

        def get_queryset(request):
            return Plaza.objects.all() if request else Plaza.objects.none()

        @server_choices(registry=registry)
        class TestShopFilterSet(FilterSet):
            plaza = filters.ModelChoiceFilter(queryset=get_queryset)

            class Meta:
                model = Shop
                fields = [
                    "plaza",
                ]

        request = HttpRequest()
        filterset = TestShopFilterSet(data=request.GET, request=request, queryset=Shop.objects.all())

        self.assertEqual(filterset.form.fields["plaza"].queryset[0], werribee_plaza)

    def test_field_widget(self):
        registry = ServerChoicesRegistry("test")

        @server_choices(registry=registry)
        class TestShopFilterSet(FilterSet):
            class Meta:
                model = Shop
                fields = [
                    "plaza",
                ]

        filterset = TestShopFilterSet()
        self.assertIsInstance(filterset.filters["plaza"].field.widget, ServerChoicesSelectWidget)

    def test_field_widget_validation(self):
        with self.assertRaisesRegex(ValueError, "widget must be either Select or SelectMultiple"):
            registry = ServerChoicesRegistry("test")

            @server_choices(registry=registry)
            class TestPaymentMethodFilterSet(FilterSet):
                shops = ModelMultipleChoiceFilter(queryset=Shop.objects.all(), widget=RadioSelect)

                class Meta:
                    model = PaymentMethod
                    fields = [
                        "shops",
                    ]
