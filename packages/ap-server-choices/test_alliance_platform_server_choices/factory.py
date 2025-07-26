from __future__ import annotations

from factory import Faker
from factory import SubFactory
from factory.django import DjangoModelFactory

from .models import PaymentMethod
from .models import Plaza
from .models import Shop
from .models import User


class AppPaymentMethodFactory(DjangoModelFactory):
    class Meta:
        model = PaymentMethod


class AppPlazaFactory(DjangoModelFactory):
    name: Faker[str, str] = Faker("name")

    class Meta:
        model = Plaza


class AppShopFactory(DjangoModelFactory):
    plaza: SubFactory[str, Plaza] = SubFactory(AppPlazaFactory)

    class Meta:
        model = Shop


class UserProfileFactory(DjangoModelFactory):
    # is_staff = True # without a good reason we dont want any part of our code to rely on is_staff

    class Meta:
        model = User
