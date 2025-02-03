from __future__ import annotations

from factory import SubFactory
from factory.django import DjangoModelFactory

from .models import PaymentMethod
from .models import Plaza
from .models import Shop


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
