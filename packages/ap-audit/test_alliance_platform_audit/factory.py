import factory
from factory.fuzzy import FuzzyInteger

from .models import AuthorProfile
from .models import MemberProfile
from .models import PaymentMethod
from .models import Plaza
from .models import Profile
from .models import Shop
from .models import SuperMemberProfile


class AppPaymentMethodFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentMethod


class AppShopFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Shop


class AppPlazaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Plaza


class ProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Profile


class AuthorProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuthorProfile


class MemberProfileFactory(factory.django.DjangoModelFactory):
    member_id = FuzzyInteger(1000, 100000)

    class Meta:
        model = MemberProfile


class SuperMemberProfileFactory(factory.django.DjangoModelFactory):
    member_id = FuzzyInteger(1000, 100000)
    award_points = FuzzyInteger(0, 100)

    class Meta:
        model = SuperMemberProfile
