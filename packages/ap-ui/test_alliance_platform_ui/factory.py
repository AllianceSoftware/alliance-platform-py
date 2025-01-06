from __future__ import annotations

from factory import Faker
from factory.django import DjangoModelFactory

from test_alliance_platform_ui.models import User


class UserFactory(DjangoModelFactory):
    email: Faker[str, str] = Faker(
        "email", domain="example.com"
    )  # reserved by IANA, sending email to these addresses wont hit
    is_superuser = False

    class Meta:
        model = User
