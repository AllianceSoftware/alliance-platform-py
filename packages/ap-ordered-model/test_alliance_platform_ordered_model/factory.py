from __future__ import annotations

from factory import SubFactory
from factory.django import DjangoModelFactory
from test_alliance_platform_ordered_model.models import Franchise
from test_alliance_platform_ordered_model.models import FranchiseLocation
from test_alliance_platform_ordered_model.models import PaymentMethod
from test_alliance_platform_ordered_model.models import Plaza
from test_alliance_platform_ordered_model.models import Shop


class AppPaymentMethodFactory(DjangoModelFactory):
    class Meta:
        model = PaymentMethod


class AppPlazaFactory(DjangoModelFactory):
    class Meta:
        model = Plaza


class AppShopFactory(DjangoModelFactory):
    plaza: SubFactory[str, Plaza] = SubFactory(AppPlazaFactory)

    class Meta:
        model = Shop


class AppFranchiseFactory(DjangoModelFactory):
    class Meta:
        model = Franchise


class AppFranchiseLocationFactory(DjangoModelFactory):
    plaza: SubFactory[str, Plaza] = SubFactory(AppPlazaFactory)
    franchise: SubFactory[str, Franchise] = SubFactory(AppFranchiseFactory)

    class Meta:
        model = FranchiseLocation
