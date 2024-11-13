from django.contrib.auth import get_user_model
from django.http import HttpResponse
import pghistory

from .models import Plaza
from .models import Shop

UserModel = get_user_model()


def test_create_plaza(request):
    if request.method == "POST":
        Plaza(name="Melbourne Central").save()
    return HttpResponse()


def test_create_shop(request):
    if request.method == "POST":
        plaza = Plaza(name="Chicken Town")
        plaza.save()
        shop = Shop(name="KFC", plaza=plaza)
        shop.save()
    return HttpResponse()


def test_create_plaza_with_context(request):
    if request.method == "POST":
        with pghistory.context(pet="banana"):
            Plaza(name="Melbourne Central").save()
    return HttpResponse()
