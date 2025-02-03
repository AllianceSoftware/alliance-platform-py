from django.db import models
from django.db.models import CASCADE
from django.db.models import QuerySet


class PaymentMethod(models.Model):
    name = models.CharField(max_length=255, blank=True)

    shops: QuerySet["Shop"]

    class Meta:
        db_table = "test_alliance_platform_server_choices_payment_method"

    def __str__(self):
        return f"{self.name}"


class Plaza(models.Model):
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "test_alliance_platform_server_choices_plaza"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ShopCategory(models.IntegerChoices):
    GROCERY = 1, "Grocery"
    SERVICES = 2, "Services"
    DEPARTMENT = 3, "Department Store"
    OTHER = 0, "Others"


class Shop(models.Model):
    name = models.CharField(max_length=255, blank=True)
    plaza = models.ForeignKey(Plaza, on_delete=CASCADE)
    category = models.PositiveSmallIntegerField(choices=ShopCategory.choices, default=ShopCategory.OTHER)
    payment_methods_accepted = models.ManyToManyField(PaymentMethod, related_name="shops", blank=True)

    class Meta:
        db_table = "test_alliance_platform_server_choices_shop"

    def __str__(self):
        return f"{self.plaza} - {self.name} ({dict(ShopCategory.choices)[self.category]})"
