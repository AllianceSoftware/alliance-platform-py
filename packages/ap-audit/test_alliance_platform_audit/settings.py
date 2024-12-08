import hashlib
import os
from pathlib import Path
import random
import re
from typing import TypedDict

from alliance_platform.audit.settings import AlliancePlatformAuditSettingsType
from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
from alliance_platform.frontend.bundler.resource_registry import FrontendResourceRegistry
from alliance_platform.frontend.settings import AlliancePlatformFrontendSettingsType

is_ci = os.environ.get("CI_SERVER", "no") == "yes"

BASE_DIR = Path(__file__).parent.parent
PROJECT_DIR = BASE_DIR
TEST_DIRECTORY = PROJECT_DIR / "test_alliance_platform_audit"

STATIC_URL = "/static/"

ROOT_URLCONF = "test_alliance_platform_storage.urls"

AUTH_USER_MODEL = "test_alliance_platform_audit.User"


class AlliancePlatformSettings(TypedDict):
    CORE: AlliancePlatformCoreSettingsType
    AUDIT: AlliancePlatformAuditSettingsType
    FRONTEND: AlliancePlatformFrontendSettingsType


frontend_registry = FrontendResourceRegistry()

ALLIANCE_PLATFORM: AlliancePlatformSettings = {
    "CORE": {
        "PROJECT_DIR": PROJECT_DIR,
    },
    "FRONTEND": {
        "FRONTEND_RESOURCE_REGISTRY": frontend_registry,
        "REACT_RENDER_COMPONENT_FILE": PROJECT_DIR / "frontend/src/renderComponent.tsx",
        "PRODUCTION_DIR": TEST_DIRECTORY / "frontend/build",
        "DEBUG_COMPONENT_OUTPUT": True,
        "BUNDLER": "test_alliance_platform_audit.bundler.vite_bundler",
        "EXTRACT_ASSETS_EXCLUDE_DIRS": (
            TEST_DIRECTORY / "codegen",
            re.compile(r".*/site-packages/.*"),
        ),
        "BUNDLER_DISABLE_DEV_CHECK_HTML": False,
        "SSR_GLOBAL_CONTEXT_RESOLVER": None,
        "NODE_MODULES_DIR": os.environ.get("NODE_MODULES_DIR", BASE_DIR.parent.parent / "node_modules"),
    },
    "AUDIT": {
        "AUDIT_LOG_COMPONENT_PATH": "audit/AuditLog",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "alliance_platform_audit",
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", None),
    }
}

INSTALLED_APPS = (
    "allianceutils",
    "alliance_platform.audit",
    "test_alliance_platform_audit",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "pghistory",
    "pgtrigger",
    "hijack",
    "rules.apps.AutodiscoverRulesConfig",
)

AUTHENTICATION_BACKENDS = [
    "test_alliance_platform_audit.auth.backends.AuditBackend",
    "rules.permissions.ObjectPermissionBackend",
]

MIDDLEWARE = (
    "django.middleware.security.SecurityMiddleware",  # various security, ssl settings (django >=1.9)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "alliance_platform.audit.middleware.AuditMiddleware",
    "hijack.middleware.HijackUserMiddleware",
)

HIJACK_PERMISSION_CHECK = "test_alliance_platform_audit.auth.backends.can_hijack"

TEMPLATE_DIRS = (
    # os.path.join(BASE_DIR, 'compat/tests/templates/')
)

TEMPLATES = (
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "DIRS": TEMPLATE_DIRS,
    },
)

STATIC_ROOT = Path(BASE_DIR, "static")

SERIALIZATION_MODULES = {
    "json_ordered": "allianceutils.serializers.json_ordered",
}

SECRET_KEY = hashlib.sha256(str(random.SystemRandom().getrandbits(256)).encode("ascii")).hexdigest()

USE_TZ = True

TIME_ZONE = "Australia/Melbourne"

# -------------------------------------
# Test case performance
PASSWORD_HASHERS = (
    #'django_plainpasswordhasher.PlainPasswordHasher', # very fast but extremely insecure
    "django.contrib.auth.hashers.SHA1PasswordHasher",  # fast but insecure
)
