from alliance_platform.audit.api import AuditLogView
from django.urls import include
from django.urls import path

from .models import test_audit_registry
from .views import test_create_plaza
from .views import test_create_plaza_with_context
from .views import test_create_shop

app_name = "test_alliance_platform_audit"


# Extend the base patterns rather than replace them. This is because various packages read
# stuff once and then cache it. Eg. hijack will read LOGIN_REDIRECT_URL and once and so if
# we try modify that or that URL doesn't exist it will break.
# django stronghold also does this; it reverses patterns and if they don't exist it silently
# ignores them and never tries again. This seemed to manifest as the ROOT_URLCONF override
# in test_audit triggered it to cache the patterns and then test_auth test cases would fail
# because login no longer worked (stronghold didn't know to exclude it)
urlpatterns = [
    # audit module testing; create a plaza
    path("create_plaza/", test_create_plaza, name="test_audit_create_plaza"),
    path("create_shop/", test_create_shop, name="test_audit_create_shop"),
    path(
        "create_plaza_with_context/",
        test_create_plaza_with_context,
        name="test_audit_create_plaza_with_context",
    ),
    path("auditlog/", AuditLogView.as_view(registry=test_audit_registry), name="test_audit_log_view"),
    path("hijack/", include("hijack.urls", namespace="hijack")),
]
